from pathlib import Path
import ctypes, struct, math, numpy as np

# Minimal Thrift compact parser for Parquet metadata/page headers
class R:
    def __init__(self,b,pos=0): self.b=b; self.i=pos
    def u8(self): v=self.b[self.i]; self.i+=1; return v
    def varint(self):
        shift=0; out=0
        while True:
            c=self.u8(); out|=(c&0x7f)<<shift
            if not c&0x80:return out
            shift+=7
    @staticmethod
    def zig(n):return (n>>1)^-(n&1)
    def i16(self):return self.zig(self.varint())
    def i32(self):return self.zig(self.varint())
    def i64(self):return self.zig(self.varint())
    def double(self): v=struct.unpack_from('<d',self.b,self.i)[0]; self.i+=8; return v
    def binary(self):
        n=self.varint(); v=self.b[self.i:self.i+n]; self.i+=n
        try:return v.decode()
        except:return bytes(v)
    def val(self,t):
        if t in (1,2):return t==1
        if t==3:return self.u8()
        if t==4:return self.i16()
        if t==5:return self.i32()
        if t==6:return self.i64()
        if t==7:return self.double()
        if t==8:return self.binary()
        if t in (9,10):
            h=self.u8(); sz=h>>4; et=h&15
            if sz==15:sz=self.varint()
            return [self.val(et) for _ in range(sz)]
        if t==11:
            sz=self.varint()
            if sz==0:return []
            h=self.u8();kt=h>>4;vt=h&15
            return [(self.val(kt),self.val(vt)) for _ in range(sz)]
        if t==12:return self.struct()
        raise ValueError(('compact type',t,self.i))
    def struct(self):
        d={};last=0
        while True:
            h=self.u8()
            if h==0:return d
            delta=h>>4;t=h&15
            fid=last+delta if delta else self.i16()
            v=(t==1) if t in (1,2) else self.val(t)
            d[fid]=v;last=fid

def read_footer(path):
    p=Path(path)
    with p.open('rb') as f:
        f.seek(-8,2); n=int.from_bytes(f.read(4),'little'); magic=f.read(4)
        if magic!=b'PAR1':raise ValueError('not parquet')
        f.seek(-(8+n),2); data=f.read(n)
    return R(data).struct()

# libsnappy
_sn=ctypes.CDLL('libsnappy.so.1')
_sn.snappy_uncompressed_length.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
_sn.snappy_uncompressed_length.restype=ctypes.c_int
_sn.snappy_uncompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t)]
_sn.snappy_uncompress.restype=ctypes.c_int

def snappy_decompress(b, expected=None):
    src=ctypes.create_string_buffer(b)
    outlen=ctypes.c_size_t()
    rc=_sn.snappy_uncompressed_length(src,len(b),ctypes.byref(outlen))
    if rc!=0:raise RuntimeError(('snappy len',rc))
    if expected and outlen.value!=expected:
        pass
    dst=ctypes.create_string_buffer(outlen.value)
    olen=ctypes.c_size_t(outlen.value)
    rc=_sn.snappy_uncompress(src,len(b),dst,ctypes.byref(olen))
    if rc!=0:raise RuntimeError(('snappy dec',rc))
    return dst.raw[:olen.value]

def read_uvarint(buf,pos):
    out=0;shift=0
    while True:
        c=buf[pos];pos+=1;out|=(c&127)<<shift
        if not c&128:return out,pos
        shift+=7

def decode_hybrid(buf, bit_width, n_values=None, pos=0):
    vals=[]; mask=(1<<bit_width)-1 if bit_width else 0
    while pos < len(buf) and (n_values is None or len(vals)<n_values):
        header,pos=read_uvarint(buf,pos)
        if header & 1 == 0:
            run=header>>1; nbytes=(bit_width+7)//8
            if bit_width==0:v=0
            else:
                v=int.from_bytes(buf[pos:pos+nbytes],'little')&mask;pos+=nbytes
            need=run if n_values is None else min(run,n_values-len(vals))
            vals.extend([v]*need)
        else:
            groups=header>>1; total=groups*8; nbits=total*bit_width; nbytes=(nbits+7)//8
            data=buf[pos:pos+nbytes];pos+=nbytes
            if bit_width==0:
                arr=[0]*total
            else:
                acc=int.from_bytes(data,'little'); arr=[(acc>>(i*bit_width))&mask for i in range(total)]
            if n_values is not None: arr=arr[:max(0,min(total,n_values-len(vals)))]
            vals.extend(arr)
    return np.asarray(vals,dtype=np.int32),pos

def plain_decode(buf, phys_type, n, pos=0):
    # Parquet physical: 0 bool,1 int32,2 int64,3 int96,4 float,5 double,6 byte_array,7 fixed
    if phys_type==5:
        a=np.frombuffer(buf,dtype='<f8',count=n,offset=pos).copy(); return a,pos+8*n
    if phys_type==4:
        a=np.frombuffer(buf,dtype='<f4',count=n,offset=pos).copy(); return a,pos+4*n
    if phys_type==2:
        a=np.frombuffer(buf,dtype='<i8',count=n,offset=pos).copy(); return a,pos+8*n
    if phys_type==1:
        a=np.frombuffer(buf,dtype='<i4',count=n,offset=pos).copy(); return a,pos+4*n
    if phys_type==6:
        out=[]
        for _ in range(n):
            ln=struct.unpack_from('<I',buf,pos)[0];pos+=4
            b=buf[pos:pos+ln];pos+=ln
            try:b=b.decode()
            except: b=bytes(b)
            out.append(b)
        return np.asarray(out,dtype=object),pos
    raise NotImplementedError(phys_type)

def read_column(path, name, out_dtype=None):
    meta=read_footer(path); schema=meta[2]; rg=meta[4][0]; names=[x.get(4) for x in schema[1:]]
    ci=names.index(name); se=schema[ci+1]; phys=se[1]; max_def=1 if se.get(3)==1 else 0
    col=rg[1][ci]; md=col[3]; start=md.get(11,md[9]); size=md[7]; nrows=meta[3]; codec=md[4]
    with open(path,'rb') as f:f.seek(start); chunk=f.read(size)
    r=R(chunk); dictionary=None; pieces=[]; nullmask_p=[]; total=0
    while r.i < len(chunk):
        h=r.struct(); comp=chunk[r.i:r.i+h[3]]; r.i+=h[3]
        raw=snappy_decompress(comp,h[2]) if codec==1 else comp
        typ=h[1]
        if typ==2:
            dh=h[7]; dictionary,_=plain_decode(raw,phys,dh[1],0)
            continue
        if typ!=0: raise NotImplementedError(('page type',typ))
        dh=h[5]; nv=dh[1]; enc=dh[2]; pos=0
        if max_def:
            lvl_len=struct.unpack_from('<I',raw,pos)[0];pos+=4
            defs,_=decode_hybrid(raw[pos:pos+lvl_len],1,nv,0);pos+=lvl_len
            defined=(defs==max_def); ndef=int(defined.sum())
        else:
            defined=np.ones(nv,dtype=bool); ndef=nv
        if enc==8:
            bw=raw[pos];pos+=1
            idx,_=decode_hybrid(raw[pos:],bw,ndef,0)
            vals=dictionary[idx]
        elif enc==0:
            vals,_=plain_decode(raw,phys,ndef,pos)
        else: raise NotImplementedError(('encoding',enc,name))
        if ndef==nv:
            arr=vals
        else:
            if phys in (4,5): arr=np.full(nv,np.nan,dtype=np.float64)
            elif phys in (1,2): arr=np.full(nv,0,dtype=np.int64)
            else: arr=np.empty(nv,dtype=object);arr[:]=None
            arr[defined]=vals
        if out_dtype is not None and getattr(arr,'dtype',None)!=object: arr=arr.astype(out_dtype,copy=False)
        pieces.append(arr); total+=nv
    out=np.concatenate(pieces)
    if len(out)!=nrows: raise RuntimeError((name,len(out),nrows,total))
    return out

if __name__=='__main__':
    path='/mnt/data/A100_2020_2026_raw.parquet'
    for nm in ['ts_code','trade_date','open','close','volume','pre_close']:
        a=read_column(path,nm)
        print(nm,len(a),a.dtype,a[:5],a[-5:])
