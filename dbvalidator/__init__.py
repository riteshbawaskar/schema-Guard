"""Thin entrypoint package so `python -m dbvalidator ...` works as documented.
All real logic lives in app.cli.main (SchemaGuard), which shares services
with the API/UI.
"""
