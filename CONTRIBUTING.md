# Contributing

Thanks for your interest in contributing to Home Bar POS!

## Ways to help

- **Report bugs** — open an issue with steps to reproduce
- **Suggest features** — open an issue describing the use case
- **Fix bugs / add features** — see workflow below
- **Improve docs** — fix typos, clarify setup steps, add examples
- **Test the Card Reader (Beta)** — especially against real Stripe/Square hardware (see README)

## Setup

```bash
git clone https://github.com/Techsociology/PointOfSales
cd PointOfSales
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`. Default login: `admin` / `admin123`.

There's no automated test suite yet — please test your changes manually in
the browser (register, admin, and shift-report screens matter most).

## Workflow

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Commit with a clear message, e.g. `fix: correct tip calculation on split tickets`
4. Push and open a Pull Request against `main`

## Guidelines

- Keep route logic in `app.py` thin; put database work in `database.py`
- UI changes should work in both dark and light theme
- Never commit anything in `instance/` (contains local DB and API keys)
- One feature/fix per PR, with a clear description (screenshots for UI changes)
- If you touch the Card Reader, say whether you tested it on real hardware, a sandbox, or neither

## Reporting bugs

Include: what you did, what you expected, what happened instead, and your
environment (OS, running from source or a packaged build, card reader
provider if relevant).

## License

By contributing, you agree your contributions are licensed under the MIT
License (see [LICENSE](LICENSE)).