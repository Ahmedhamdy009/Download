# Nazzelha: local and online use

## Local Windows use

1. Keep `app.py`, `website/`, `yt-dlp.exe`, and `ffmpeg.exe` in this folder.
2. Double-click `تشغيل التطبيق.bat`.
3. Open `http://127.0.0.1:8765/` on this computer. To use a phone on the same Wi-Fi, use the computer's local IP address with port `8765`.

The local launcher does not need a hosting account. Keep its console open while downloading.

## Online deployment

The project includes `Dockerfile` and `render.yaml` for a Render web service. The online service must use a Linux runtime and the included `APP_PASSWORD` setting; do not put the password in Git or in this file.

To make the URL available from outside the home network, the source must be placed in a private GitHub repository and connected to a Render account. During service creation, Render asks for `APP_PASSWORD`; choose a password there. The app then asks for those credentials when opened. The free service can sleep while idle, and downloaded files live only in temporary container storage.

See Render's current [free-service limits](https://render.com/docs/free) before relying on it.
