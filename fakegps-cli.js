#!/usr/bin/env node
/**
 * FakeGPS CLI entry point
 * Auto-downloads the correct platform binary from GitHub Releases on first run.
 * Zero external dependencies — uses only Node.js built-in modules.
 */

const os = require('os');
const path = require('path');
const fs = require('fs');
const https = require('https');
const { spawn } = require('child_process');

const GITHUB_REPO = 'sixzjd/fakeGPS-for-iPhone';
const CACHE_DIR = path.join(os.homedir(), '.fakegps');
const VERSION_FILE = path.join(CACHE_DIR, 'version');

// ── Platform detection ──

function getPlatformConfig() {
  const platform = os.platform();
  if (platform === 'darwin') {
    const arch = os.arch();
    return {
      name: 'macOS',
      zipName: 'FakeGPS-macOS.zip',
      binaryPath: 'FakeGPS.app/Contents/MacOS/FakeGPS',
      extractDir: 'FakeGPS.app',
    };
  }
  if (platform === 'win32') {
    return {
      name: 'Windows',
      zipName: 'FakeGPS-Windows.zip',
      binaryPath: 'FakeGPS/FakeGPS.exe',
      extractDir: 'FakeGPS',
    };
  }
  console.error(`❌ Unsupported platform: ${platform}`);
  console.error('FakeGPS supports macOS and Windows only.');
  process.exit(1);
}

// ── GitHub API ──

function httpsGet(url) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: { 'User-Agent': 'fakegps-npm' } }, (res) => {
      // Handle redirects (302)
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return httpsGet(res.headers.location).then(resolve).catch(reject);
      }
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString() }));
      res.on('error', reject);
    });
    req.on('error', reject);
  });
}

function httpsDownload(url, dest, onProgress) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: { 'User-Agent': 'fakegps-npm' } }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return httpsDownload(res.headers.location, dest, onProgress).then(resolve).catch(reject);
      }
      if (res.statusCode !== 200) {
        reject(new Error(`Download failed: HTTP ${res.statusCode}`));
        return;
      }
      const total = parseInt(res.headers['content-length'] || '0', 10);
      let downloaded = 0;
      const stream = fs.createWriteStream(dest);
      res.on('data', (chunk) => {
        downloaded += chunk.length;
        if (onProgress && total) {
          const pct = Math.round((downloaded / total) * 100);
          const mb = (downloaded / 1024 / 1024).toFixed(1);
          const totalMb = (total / 1024 / 1024).toFixed(1);
          onProgress(pct, mb, totalMb);
        }
      });
      res.pipe(stream);
      stream.on('finish', () => { stream.close(); resolve(); });
      stream.on('error', reject);
      res.on('error', reject);
    });
    req.on('error', reject);
  });
}

async function getLatestRelease() {
  const res = await httpsGet(`https://api.github.com/repos/${GITHUB_REPO}/releases/latest`);
  if (res.status !== 200) {
    throw new Error(`Failed to check releases: HTTP ${res.status}`);
  }
  return JSON.parse(res.body);
}

// ── ZIP extraction ──

function extractZip(zipPath, destDir) {
  // Try unzip (macOS/Linux) or PowerShell (Windows)
  return new Promise((resolve, reject) => {
    let proc;
    if (os.platform() === 'win32') {
      proc = spawn('powershell', [
        '-NoProfile', '-Command',
        `Expand-Archive -Path '${zipPath}' -DestinationPath '${destDir}' -Force`
      ]);
    } else {
      proc = spawn('unzip', ['-o', '-q', zipPath, '-d', destDir]);
    }
    proc.on('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`Extraction failed with code ${code}`));
    });
    proc.on('error', reject);
  });
}

// ── Main ──

async function ensureBinary() {
  const config = getPlatformConfig();
  const binaryPath = path.join(CACHE_DIR, config.binaryPath);

  // Check if binary already exists and is current
  if (fs.existsSync(binaryPath)) {
    // Read version file to see if we need an update
    if (fs.existsSync(VERSION_FILE)) {
      return { config, binaryPath };
    }
  }

  console.log(`\n🚀 FakeGPS — First run on ${config.name}`);
  console.log('   Downloading the latest binary from GitHub Releases...\n');

  // Create cache directory
  fs.mkdirSync(CACHE_DIR, { recursive: true });

  // Get latest release info
  const release = await getLatestRelease();
  const asset = release.assets.find(a => a.name === config.zipName);
  if (!asset) {
    throw new Error(
      `No ${config.zipName} found in release ${release.tag_name}.\n` +
      `Available: ${release.assets.map(a => a.name).join(', ')}`
    );
  }

  // Download
  const zipPath = path.join(CACHE_DIR, config.zipName);
  console.log(`   ⬇ ${asset.name} (${(asset.size / 1024 / 1024).toFixed(1)} MB)`);
  console.log(`   Release: ${release.tag_name} — ${release.name || ''}`);
  console.log('');

  let lastPct = -1;
  await httpsDownload(asset.browser_download_url, zipPath, (pct, mb, total) => {
    if (pct !== lastPct && pct % 5 === 0) {
      const bar = '█'.repeat(Math.floor(pct / 5)) + '░'.repeat(20 - Math.floor(pct / 5));
      process.stdout.write(`\r   [${bar}] ${pct}% (${mb}/${total} MB)`);
      lastPct = pct;
    }
  });
  console.log('\n');

  // Extract
  console.log('   📦 Extracting...');
  await extractZip(zipPath, CACHE_DIR);

  // Save version info
  fs.writeFileSync(VERSION_FILE, `${release.tag_name}\n${config.zipName}\n`);

  // Make binary executable on macOS
  if (os.platform() === 'darwin') {
    try { fs.chmodSync(binaryPath, 0o755); } catch (e) {}
  }

  // Clean up zip
  try { fs.unlinkSync(zipPath); } catch (e) {}

  console.log('   ✅ Ready!\n');
  return { config, binaryPath };
}

async function main() {
  try {
    const { binaryPath } = await ensureBinary();

    // Forward all arguments to the binary
    const args = process.argv.slice(2);
    const proc = spawn(binaryPath, args, { stdio: 'inherit' });
    proc.on('close', (code) => process.exit(code));
    proc.on('error', (err) => {
      console.error(`❌ Failed to launch FakeGPS: ${err.message}`);
      console.error(`   Binary: ${binaryPath}`);
      process.exit(1);
    });
  } catch (err) {
    console.error(`❌ ${err.message}`);
    process.exit(1);
  }
}

main();
