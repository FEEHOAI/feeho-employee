# Contributing

Thanks for improving the open employee-package contract.

## Ground rules

- Keep the core model-agnostic and portable.
- Do not submit credentials, customer data, private enterprise packages or third-party reference screenshots.
- A schema-valid package is not automatically an accepted employee; preserve that distinction.
- Add tests for behavior changes and run `python -m unittest discover -s tests -v`.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -v
```

Open an issue before large schema changes. Keep v0.1 assertions explicit and deterministic.

## Developer Certificate of Origin

Contributions are licensed under MIT. Sign off each commit with `git commit -s`. The sign-off adds:

```text
Signed-off-by: Your Name <you@example.com>
```

By signing off, you certify the following DCO 1.1:

> By making a contribution to this project, I certify that:
> (a) The contribution was created in whole or in part by me and I have the right to submit it under the open source license indicated in the file; or
> (b) The contribution is based upon previous work that, to the best of my knowledge, is covered under an appropriate open source license and I have the right under that license to submit that work with modifications, whether created in whole or in part by me, under the same open source license (unless I am permitted to submit under a different license), as indicated in the file; or
> (c) The contribution was provided directly to me by some other person who certified (a), (b) or (c) and I have not modified it.
> (d) I understand and agree that this project and the contribution are public and that a record of the contribution (including all personal information I submit with it, including my sign-off) is maintained indefinitely and may be redistributed consistent with this project or the open source license(s) involved.

No separate CLA is currently represented as accepted or signed. Commercial agreements for enterprise features are handled separately and do not remove MIT rights in this repository.
