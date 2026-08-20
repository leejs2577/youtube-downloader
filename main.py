from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import os
import uuid
import asyncio

app = FastAPI(title="YouTube Downloader API")

# Mount the static directory for the frontend
app.mount("/static", StaticFiles(directory="static", html=True), name="static")

TEMP_DIR = "temp_downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

class DownloadRequest(BaseModel):
    url: str
    format_type: str # "video" or "audio"
    resolution: str = "best" # e.g. "1080p", "720p", "best"

def get_video_info(url: str):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True
    }
    
    # 쿠키 파일이 존재하면 적용 (봇 차단 우회용)
    if os.path.exists("cookies.txt"):
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
        raise Exception(f"Failed to fetch video info: {str(e)}")

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
        
        ydl_opts = {
            'outtmpl': outtmpl,
            'quiet': True,
            'no_warnings': True
        }
        
        # 쿠키 파일이 존재하면 적용 (봇 차단 우회용)
        if os.path.exists("cookies.txt"):
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
        raise HTTPException(status_code=400, detail=f"Download failed: {str(e)}")
