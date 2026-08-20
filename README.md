# YouTube Downloader

## Render deployment

YouTube can reject requests from Render's shared data-center IP addresses as automated traffic. Do not commit `cookies.txt` or copy it into the Docker image.

1. Export fresh YouTube cookies in **Netscape** format from a browser session you control.
2. In PowerShell, create a single-line value:

   ```powershell
   [Convert]::ToBase64String([IO.File]::ReadAllBytes('cookies.txt'))
   ```

3. In Render, open the service's **Environment** settings and add the secret environment variable `YTDLP_COOKIES_B64` with that value.
4. Redeploy the service. Refresh the cookie secret whenever YouTube blocks requests again.

The application writes this secret only to `/tmp/ytdlp-cookies.txt` while the container runs. For local development only, an untracked `cookies.txt` file is still supported.
