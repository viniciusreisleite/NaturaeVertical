import os
import glob
import json
import subprocess
import time
from playwright.sync_api import sync_playwright

def cleanup_old_videos(allowed_files):
    """Deleta qualquer arquivo de vídeo que não esteja na lista dos 12 permitidos"""
    for file_path in glob.glob("video_*.mp4"):
        if file_path not in allowed_files:
            try:
                os.remove(file_path)
                print(f"🗑️ Arquivo antigo removido: {file_path}")
            except Exception as e:
                print(f"Erro ao remover {file_path}: {e}")

def main():
    cookies_raw = os.environ.get("INSTAGRAM_COOKIES", "")
    cookie_file = "cookies.txt"
    with open(cookie_file, "w", encoding="utf-8") as f:
        f.write(cookies_raw)

    playwright_cookies = []
    for line in cookies_raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            domain, _, path, secure, expires, name, value = parts[:7]
            playwright_cookies.append({
                "name": name,
                "value": value,
                "domain": domain,
                "path": path,
                "secure": secure.lower() == "true",
                "expires": float(expires) if expires.isdigit() else -1
            })

    username = "naturae_nutribar"
    target_count = 12
    reels_urls = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        
        if playwright_cookies:
            context.add_cookies(playwright_cookies)

        page = context.new_page()
        print(f"Acessando Reels de @{username} com ordenação cronológica estrita...")

        try:
            page.goto(f"https://www.instagram.com/{username}/reels/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

            # Varredura progressiva ordenada por coordenadas visuais
            for scroll_step in range(8):
                raw_items = page.evaluate("""() => {
                    const links = Array.from(document.querySelectorAll("a[href*='/reel/'], a[href*='/p/']"));
                    return links.map(el => {
                        const rect = el.getBoundingClientRect();
                        const isPinned = !!el.querySelector("svg[aria-label*='Pin'], svg[aria-label*='Fixado'], svg[title*='Pin'], svg[title*='Fixado'], svg[aria-label*='Pinned']");
                        return {
                            href: el.getAttribute('href'),
                            top: Math.round(rect.top + window.scrollY),
                            left: Math.round(rect.left),
                            isPinned: isPinned
                        };
                    });
                }""")

                # Ordena rigorosamente: primeiro por linha (top), depois por coluna (left)
                raw_items.sort(key=lambda item: (item['top'], item['left']))

                for item in raw_items:
                    if item.get("isPinned"):
                        continue
                    href = item.get("href")
                    if href:
                        full_url = f"https://www.instagram.com{href}" if href.startswith("/") else href
                        clean_url = full_url.split("?")[0]
                        if clean_url not in reels_urls:
                            reels_urls.append(clean_url)

                if len(reels_urls) >= target_count:
                    break

                page.mouse.wheel(0, 800)
                time.sleep(2)

        except Exception as e:
            print(f"Aviso durante navegação: {e}")

        browser.close()

    reels_urls = reels_urls[:target_count]
    print(f"\nTotal de Reels identificados em ordem cronológica: {len(reels_urls)}")
    for i, url in enumerate(reels_urls, 1):
        print(f"  #{i} -> {url}")

    if not reels_urls:
        print("❌ Nenhum Reel foi identificado.")
        return

    posts_data = []
    allowed_videos = [f"video_{i}.mp4" for i in range(1, len(reels_urls) + 1)]

    for idx, reel_url in enumerate(reels_urls, start=1):
        print(f"\n--- Baixando Reel #{idx} (Mais recente): {reel_url} ---")
        output_filename = f"video_{idx}.mp4"
        temp_raw = f"temp_raw_{idx}.mp4"

        cmd_download = [
            "yt-dlp",
            "--cookies", cookie_file,
            "--no-check-certificates",
            "-f", "bestvideo+bestaudio/best",
            "-o", temp_raw,
            "--force-overwrites",
            reel_url
        ]
        subprocess.run(cmd_download, capture_output=True, text=True)

        if os.path.exists(temp_raw):
            cmd_ffmpeg = [
                "ffmpeg", "-y",
                "-i", temp_raw,
                "-vf", "scale='min(720,iw)':-2",
                "-c:v", "libx264",
                "-crf", "26",
                "-preset", "veryfast",
                "-c:a", "aac",
                "-b:a", "96k",
                "-movflags", "+faststart",
                output_filename
            ]
            subprocess.run(cmd_ffmpeg, capture_output=True, text=True)
            try:
                os.remove(temp_raw)
            except Exception:
                pass

        posts_data.append({
            "id": idx,
            "url": reel_url,
            "video_file": output_filename,
            "updated_at": time.strftime("%d/%m/%Y às %H:%M")
        })

    cleanup_old_videos(allowed_videos)

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(posts_data, f, ensure_ascii=False, indent=2)

    if os.path.exists(cookie_file):
        os.remove(cookie_file)

    print("\n✅ Concluído! 12 Reels em ordem cronológica perfeita salvos com sucesso.")

if __name__ == "__main__":
    main()
