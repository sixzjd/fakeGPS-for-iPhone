# FakeGPS Project — Agent Instructions

## Release Workflow

### Version Bump Locations (all must match)

| File | Pattern |
|------|---------|
| `package.json` | `"version": "X.Y.Z"` |
| `fakegps/__init__.py` | `__version__ = "X.Y.Z"` |
| `fakegps/gui.py` | `title="FakeGPS vX.Y.Z"` |
| `fakegps/ui.html` | `<div class="app-version">vX.Y.Z</div>` |
| `fakegps/cli.py` (2 places) | `"FakeGPS vX.Y.Z"` |
| `setup.py` | `version="X.Y.Z"` |

### Steps

1. **Bump version** in all 6 files above to the same value
2. **Clean up**: remove `__pycache__/`, `build/`, `dist/`, `*.egg-info/`, `.DS_Store`
3. **Commit & push**: `git add -A && git commit -m "release: vX.Y.Z" && git push origin main`
   - Use `GH_TOKEN=$(gh auth token) git -c credential.helper="!f() { echo username=x-access-token; echo password=$(gh auth token); }; f" push origin main` if SSH fails
4. **Trigger CI**: `gh workflow run build.yml -f release_tag=vX.Y.Z`
   - CI builds macOS + Windows via PyInstaller, uploads zips to GitHub Release automatically
5. **Verify release**: `gh release view vX.Y.Z --json assets --jq '.assets[].name'` — should show `FakeGPS-macOS.zip` + `FakeGPS-Windows.zip`
6. **Publish npm**: `cd ~/Desktop/release && npm publish` (may need `--otp=XXXXXX`)
7. **Update website** (`/tmp/website-repo/index.html`): change version badge `<span>vX.Y.Z</span>`
8. **Update Homebrew** (`/tmp/homebrew-fakegps/Casks/fakegps.rb`): update `version` + `sha256` (compute from downloaded zip)

### Pitfalls

- Do NOT add `distutils` to `EXCLUDED_MODULES` in `fakegps.spec` (breaks Windows Python 3.12)
- `fakegps.spec` uses `hook_stub_modules.py` runtime hook to exclude heavy deps (~50MB savings)
- Download links: `https://gh-proxy.com/https://github.com/sixzjd/fakeGPS-for-iPhone/releases/latest/download/FakeGPS-{macOS|Windows}.zip`
- npm `fakegps-cli.js` auto-detects platform and downloads correct binary from GitHub Release
