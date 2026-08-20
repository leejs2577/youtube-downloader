from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import os
import uuid
import asyncio
import base64
import binascii
import tempfile
from pathlib import Path

app = FastAPI(title="YouTube Downloader API")

# Mount the static directory for the frontend
app.mount("/static", StaticFiles(directory="static", html=True), name="static")

TEMP_DIR = "temp_downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

COOKIES_ENV_NAME = "YTDLP_COOKIES_B64"
RUNTIME_COOKIES_FILE = Path(tempfile.gettempdir()) / "ytdlp-cookies.txt"


def get_cookiefile() -> str | None:
    """Load production cookies from an environment secret, never the image."""
    encoded_cookies = os.getenv(COOKIES_ENV_NAME, "").strip()
    if encoded_cookies:
        try:
            cookies = base64.b64decode(encoded_cookies, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RuntimeError(
                f"{COOKIES_ENV_NAME} must be a valid base64-encoded Netscape cookie file."
            ) from exc

        if not cookies.lstrip().startswith(b"# Netscape HTTP Cookie File"):
            raise RuntimeError(
                f"{COOKIES_ENV_NAME} must contain a Netscape-format cookie file."
            )

        RUNTIME_COOKIES_FILE.write_bytes(cookies)
        os.chmod(RUNTIME_COOKIES_FILE, 0o600)
        return str(RUNTIME_COOKIES_FILE)

    local_cookiefile = Path("cookies.txt")
    return str(local_cookiefile) if local_cookiefile.exists() else None


def build_ydl_options(**options):
    cookiefile = get_cookiefile()
    if cookiefile:
        options["cookiefile"] = cookiefile
    return options


def user_facing_ytdlp_error(exc: Exception) -> str:
    message = str(exc)
    if "Sign in to confirm you're not a bot" in message or "Sign in to confirm youre not a bot" in message:
        return (
            "YouTube blocked this server request as automated traffic. "
            "Set a current YTDLP_COOKIES_B64 Render environment variable, then redeploy."
        )
    return message

class DownloadRequest(BaseModel):
    url: str
    format_type: str # "video" or "audio"
    resolution: str = "best" # e.g. "1080p", "720p", "best"

def get_video_info(url: str):
    ydl_opts = build_ydl_options(quiet=True, no_warnings=True)
    
    # 쿠키 파일이 존재하면 적용 (봇 차단 우회용)
    if not ydl_opts.get("cookiefile") and os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = 'cookies.txt'
        
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Extract available resolutions
            resolutions = set()
            if 'formats' in info:
                for f in info['formats']:
                    if f.get('vcodec') != 'none' and f.get('height'):
                        resolutions.add(f"{f['height']}p")
            
            # Sort resolutions descending
            sorted_res = sorted(list(resolutions), key=lambda x: int(x.replace('p', '')), reverse=True)
            
            return {
                "title": info.get("title", "Unknown Title"),
                "thumbnail": info.get("thumbnail", ""),
                "resolutions": sorted_res
            }
    except Exception as e:
        raise Exception(f"Failed to fetch video info: {user_facing_ytdlp_error(e)}") from e

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

@app.get("/api/info")
def fetch_info(url: str):
    try:
        info = get_video_info(url)
        return info
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

def remove_file(path: str):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        print(f"Error removing file {path}: {e}")

@app.post("/api/download")
async def download_media(req: DownloadRequest, background_tasks: BackgroundTasks):
    try:
        # Generate a unique ID for the filename
        file_id = str(uuid.uuid4())
        outtmpl = os.path.join(TEMP_DIR, f"{file_id}_%(title)s.%(ext)s")
        
        ydl_opts = build_ydl_options(
            outtmpl=outtmpl,
            quiet=True,
            no_warnings=True,
        )
        
        # 쿠키 파일이 존재하면 적용 (봇 차단 우회용)
        if not ydl_opts.get("cookiefile") and os.path.exists("cookies.txt"):
            ydl_opts['cookiefile'] = 'cookies.txt'
            
        if req.format_type == "audio":
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:
            # Video
            if req.resolution and req.resolution != "best":
                height = req.resolution.replace('p', '')
                ydl_opts['format'] = f'bestvideo[height<={height}]+bestaudio/best'
            else:
                ydl_opts['format'] = 'bestvideo+bestaudio/best'
            
            ydl_opts['merge_output_format'] = 'mp4'

        # Since yt-dlp is blocking, we run it in a thread
        loop = asyncio.get_event_loop()
        
        def run_ytdlp():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(req.url, download=True)
                # If audio was extracted to mp3, extension might change, let's get the final filename
                return ydl.prepare_filename(info)
        
        downloaded_file = await loop.run_in_executor(None, run_ytdlp)
        
        # In case of postprocessing (e.g. mp3 conversion), the extension might change
        if req.format_type == "audio":
            # yt-dlp changes the extension to .mp3 after postprocessing
            base, _ = os.path.splitext(downloaded_file)
            downloaded_file = f"{base}.mp3"
        elif req.format_type == "video":
            # For merge_output_format mp4
            base, _ = os.path.splitext(downloaded_file)
            downloaded_file = f"{base}.mp4"
            
        if not os.path.exists(downloaded_file):
             raise HTTPException(status_code=500, detail="Downloaded file not found.")

        # Schedule the file to be deleted after the response is sent
        background_tasks.add_task(remove_file, downloaded_file)
        
        filename = os.path.basename(downloaded_file)
        # Remove the uuid prefix from the download filename sent to the user
        display_name = filename.replace(f"{file_id}_", "")
        
        return FileResponse(
            path=downloaded_file, 
            filename=display_name,
            media_type="application/octet-stream"
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Download failed: {user_facing_ytdlp_error(e)}") from e
