# Maker Swap

Maker Swap is a second-hand marketplace demo for makers and hobbyists, built for the CognitioLabs Associate Forward Deployed Engineer assessment.

## Local setup

1. Create and activate a Python virtual environment.
2. Install development dependencies with `python -m pip install -r requirements-dev.txt`.
3. Set `CLASSGW_KEY` in your local environment; never commit it.
4. Run `uvicorn app.main:app --reload`.
5. Open `http://127.0.0.1:8000`.

Run tests with `python -m pytest`.

## Deployment

The included `render.yaml` defines one Render web service. Set `CLASSGW_KEY` as a secret environment variable in Render before enabling AI features.

