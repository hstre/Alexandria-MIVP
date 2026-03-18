# Release Checklist

Use this checklist before tagging a new release of `alexandria-mivp`.

## 1. Code quality

- [ ] All tests pass: `pytest tests/ -q`
- [ ] No warnings in test output
- [ ] `pip install -e ".[dev]"` succeeds on a clean environment
- [ ] `python -c "import alexandria_mivp; print(alexandria_mivp.__version__)"` prints expected version

## 2. Version bump

- [ ] Update `version` in `pyproject.toml`
- [ ] Update `version` in `setup.py`
- [ ] Update `__version__` in `alexandria_mivp/__init__.py`
- [ ] All three version strings are identical

## 3. Documentation

- [ ] `README.md` reflects current API (imports, class names, examples)
- [ ] `UPDATES.md` has a dated entry describing all notable changes since last release
- [ ] Module maturity table in `README.md` is up-to-date

## 4. Packaging

- [ ] `python -m build` produces a valid sdist and wheel (no errors)
- [ ] `twine check dist/*` passes (if publishing to PyPI)
- [ ] Optional extras install without errors:
  - `pip install -e ".[signatures]"`
  - `pip install -e ".[s3]"`
  - `pip install -e ".[ipfs]"`

## 5. Git hygiene

- [ ] Working tree is clean (`git status` shows nothing uncommitted)
- [ ] All changes are on a feature branch and merged to `master` via PR
- [ ] Branch is up-to-date with `master`

## 6. Tagging

```bash
git tag -a v<VERSION> -m "Release v<VERSION>"
git push origin v<VERSION>
```

## 7. Post-release

- [ ] Verify the tag appears on GitHub
- [ ] Update any dependent projects that pin this package
