# Security

- Store `HITHINK_FINANCE_API_KEY` only in GitHub Actions repository secrets.
- Never place the key in source files, workflow YAML, Issues, logs, Pages, URLs, or ChatGPT messages.
- GitHub Pages output is intentionally sanitized and contains no credentials.
- If a key is ever exposed, revoke/rotate it at HiThink immediately and replace the repository secret.
