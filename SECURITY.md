# Security

## Model

dcim is a command line program that **reads and writes a SQLite database and a few files**. It starts no service, opens no network
connection and runs no code from its input.

- **What it reads:** the database (all queries are parameterised; the schema has foreign keys and CHECK constraints and a
  `user_version`, and a file that is not a dcim database is refused), the facility JSON and inventory CSV given to `import`, the truth
  JSON given to `check --truth` and `report --truth`, and a `report.json` or `bench.json` given to `render`.
- **What it writes:** only where the options say: the database, `generate DIR` (it refuses to overwrite its files), `elevation -o`,
  `export -o`, `report --out`, `bench --out` and `render -o` and `--figure`.
- **Names are untrusted text.** Device and rack names are escaped in the SVG and in the HTML page; a test puts markup in them.
- **The Docker image** runs as an unprivileged user and works with a read-only root filesystem (plus `--tmpfs /tmp` for matplotlib's
  cache), no capabilities and no network (`--network none`); see `tools/docker_e2e.sh`.
- **No real data** is in the repository: the data centers are synthetic. A database of your own describes where your equipment is
  and how it is wired; keep it private and run the tool locally, as the image is built to be run.

## Reporting

If you find a vulnerability, please open a private security advisory on the GitHub repository (Security tab) rather than a public
issue.
