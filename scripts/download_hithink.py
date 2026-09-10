def fetch(kind,dest):

    import subprocess

    tmp = dest.with_suffix(
        dest.suffix + ".part"
    )

    last_error=None


    for attempt in range(1,9):

        try:

            url = presigned(kind)


            cmd=[
                "curl",
                "-L",
                "--fail",
                "--retry",
                "8",
                "--retry-delay",
                "10",
                "--retry-connrefused",
                "-C",
                "-",
                "-o",
                str(tmp),
                url
            ]


            print(
                f"{kind}: curl download attempt {attempt}",
                flush=True
            )


            subprocess.run(
                cmd,
                check=True
            )


            size=tmp.stat().st_size


            if size < 1024:

                raise RuntimeError(
                    f"{kind}: file too small {size}"
                )


            tmp.replace(dest)

            print(
                f"{kind}: download completed "
                f"{size} bytes",
                flush=True
            )


            return size


        except Exception as e:

            last_error=e

            print(
                f"{kind}: attempt {attempt} failed: {e}",
                flush=True
            )

            time.sleep(
                min(
                    attempt*15,
                    120
                )
            )


    raise RuntimeError(
        f"{kind}: failed after retries: {last_error}"
    )
