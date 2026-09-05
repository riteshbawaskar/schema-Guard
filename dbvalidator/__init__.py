"""Thin entrypoint package so `python -m dbvalidator ...` works as documented.
All real logic lives in app.cli.main (SchemaSentry), which shares services
with the API/UI.
"""
