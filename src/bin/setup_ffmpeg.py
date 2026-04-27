"""Download and setup FFmpeg binary."""

import os
import sys
import platform
import zipfile
import shutil
from pathlib import Path

def _download_with_progress(url, dest_file):
    """Download file with progress bar."""
    import urllib.request

    def _progress_hook(block_num, block_size, total_size):
        """Progress hook for urlretrieve."""
        if total_size < 0:
            return

        downloaded = block_num * block_size
        percent = min(100, int(100.0 * downloaded / total_size))

        bar_length = 40
        filled = int(bar_length * percent / 100)
        bar = "█" * filled + "░" * (bar_length - filled)

        if downloaded > total_size:
            downloaded = total_size

        mb_downloaded = downloaded / (1024 * 1024)
        mb_total = total_size / (1024 * 1024)

        sys.stdout.write(f"\r[{bar}] {percent:3d}% ({mb_downloaded:.1f}MB / {mb_total:.1f}MB)")
        sys.stdout.flush()

    urllib.request.urlretrieve(url, dest_file, reporthook=_progress_hook)


def get_ffmpeg_url():
    """Get FFmpeg download URL based on OS."""
    system = platform.system()
    if system == "Windows":
        return "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    elif system == "Linux":
        return "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
    elif system == "Darwin":
        return "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-macos64-gpl.tar.xz"
    else:
        raise RuntimeError(f"Unsupported OS: {system}")

def download_ffmpeg(url, dest_dir):
    """Download FFmpeg and extract to dest_dir."""
    print(f"Downloading FFmpeg from {url}...")

    # Create temp file
    temp_file = os.path.join(dest_dir, "ffmpeg_temp.zip" if url.endswith(".zip") else "ffmpeg_temp.tar.xz")

    try:
        _download_with_progress(url, temp_file)
        print(f"\nDownloaded to {temp_file}")

        # Extract
        print("\nExtracting FFmpeg...")
        if url.endswith(".zip"):
            with zipfile.ZipFile(temp_file, 'r') as zip_ref:
                zip_ref.extractall(dest_dir)
        else:
            import tarfile
            with tarfile.open(temp_file, 'r:xz') as tar_ref:
                tar_ref.extractall(dest_dir)

        print("✓ Extraction complete")

        # Find ffmpeg binary in extracted contents
        system = platform.system()
        ext = ".exe" if system == "Windows" else ""

        # Search for ffmpeg binary
        for root, dirs, files in os.walk(dest_dir):
            if f"ffmpeg{ext}" in files:
                src = os.path.join(root, f"ffmpeg{ext}")
                dst = os.path.join(dest_dir, f"ffmpeg{ext}")
                if src != dst:
                    shutil.copy2(src, dst)
                    print(f"Copied ffmpeg{ext} to {dst}")

                # Also copy ffplay if available
                if f"ffplay{ext}" in files:
                    src_play = os.path.join(root, f"ffplay{ext}")
                    dst_play = os.path.join(dest_dir, f"ffplay{ext}")
                    if src_play != dst_play:
                        shutil.copy2(src_play, dst_play)
                        print(f"Copied ffplay{ext} to {dst_play}")
                break

        # Clean up extracted directory and temp file
        for root, dirs, files in os.walk(dest_dir):
            for d in dirs:
                dir_path = os.path.join(root, d)
                if os.path.basename(dir_path).startswith("ffmpeg-"):
                    shutil.rmtree(dir_path)
                    print(f"Cleaned up {dir_path}")

        if os.path.exists(temp_file):
            os.remove(temp_file)

        print("FFmpeg setup complete!")
        return True

    except Exception as e:
        print(f"Error downloading FFmpeg: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

def main():
    """Main setup function."""
    # Determine destination directory (src/bin/)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dest_dir = script_dir

    print(f"Setting up FFmpeg in {dest_dir}")

    # Check if ffmpeg already exists
    ext = ".exe" if platform.system() == "Windows" else ""
    ffmpeg_path = os.path.join(dest_dir, f"ffmpeg{ext}")

    if os.path.exists(ffmpeg_path):
        print(f"FFmpeg already exists at {ffmpeg_path}")
        return

    # Create bin directory if it doesn't exist
    os.makedirs(dest_dir, exist_ok=True)

    # Download and extract
    url = get_ffmpeg_url()
    if download_ffmpeg(url, dest_dir):
        # Verify ffmpeg was installed
        if os.path.exists(ffmpeg_path):
            print(f"✓ FFmpeg successfully installed at {ffmpeg_path}")
            os.chmod(ffmpeg_path, 0o755)
        else:
            print(f"✗ FFmpeg not found at {ffmpeg_path}")
            sys.exit(1)
    else:
        print("✗ Failed to download FFmpeg")
        sys.exit(1)

if __name__ == "__main__":
    main()
