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
6. **Upload to Cloudflare R2**: download from GitHub then upload to R2 CDN
   ```bash
   gh release download vX.Y.Z --pattern "FakeGPS-macOS.zip" --dir /tmp
   gh release download vX.Y.Z --pattern "FakeGPS-Windows.zip" --dir /tmp
   wrangler r2 object put fakegps-releases/latest/FakeGPS-macOS.zip --file=/tmp/FakeGPS-macOS.zip --remote
   wrangler r2 object put fakegps-releases/latest/FakeGPS-Windows.zip --file=/tmp/FakeGPS-Windows.zip --remote
   ```
7. **Publish npm**: `cd ~/Desktop/release && npm publish` (may need `--otp=XXXXXX`)
8. **Update website** (`/tmp/website-repo/index.html`): change version badge `<span>vX.Y.Z</span>`
9. **Update Homebrew** (`/tmp/homebrew-fakegps/Casks/fakegps.rb`): update `version` + `sha256` (compute from downloaded zip)

### Download Infrastructure

- **Primary**: Cloudflare R2 CDN — `https://pub-6ba76a8ad6144022816bc12a211986f4.r2.dev/latest/FakeGPS-{macOS|Windows}.zip`
- **Fallback**: GitHub proxy — `https://gh-proxy.com/https://github.com/sixzjd/fakeGPS-for-iPhone/releases/latest/download/FakeGPS-{macOS|Windows}.zip`
- npm `fakegps-cli.js` tries R2 first, falls back to gh-proxy automatically

### Pitfalls

- Do NOT add `distutils` to `EXCLUDED_MODULES` in `fakegps.spec` (breaks Windows Python 3.12)
- `fakegps.spec` uses `hook_stub_modules.py` runtime hook to exclude heavy deps (~50MB savings)
- npm `fakegps-cli.js` auto-detects platform and downloads correct binary (R2 first, gh-proxy fallback)
