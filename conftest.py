"""
pytest configuration – makes the installed package available for all tests.

Run from the project root:
    pytest              # all tests
    pytest tests/       # same
"""
# Nothing needed here: after `pip install -e .` the package is importable
# as `alexandria_mivp` from anywhere. The conftest.py exists to signal to
# pytest that this is the project root and to set the rootdir correctly.
