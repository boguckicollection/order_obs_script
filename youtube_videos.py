import os
import json
import requests
from datetime import datetime


def load_env_file(path: str = '.env') -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key, value)


def fetch_videos():
    api_key = os.getenv('YT_API_KEY')
    channel_id = os.getenv('YT_CHANNEL_ID')
    output_path = os.getenv('VIDEOS_OUTPUT_PATH', 'videos.json')
    max_results = int(os.getenv('YT_MAX_RESULTS', '4'))

    if not api_key or not channel_id:
        print('YT_API_KEY or YT_CHANNEL_ID not set')
        return

    url = 'https://www.googleapis.com/youtube/v3/search'
    params = {
        'key': api_key,
        'channelId': channel_id,
        'part': 'snippet',
        'order': 'date',
        'maxResults': max_results,
        'type': 'video'
    }

    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        videos = []
        for item in data.get('items', []):
            vid = item['id'].get('videoId')
            if not vid:
                continue
            snippet = item['snippet']
            videos.append({
                'id': vid,
                'title': snippet.get('title', ''),
                'thumbnail': snippet.get('thumbnails', {}).get('medium', {}).get('url', ''),
                'publishedAt': snippet.get('publishedAt')
            })

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(videos, f, indent=2, ensure_ascii=False)
        print(f'Saved {output_path} with {len(videos)} videos at {datetime.now()}')
    except Exception as e:
        print('Failed to fetch videos:', e)


if __name__ == '__main__':
    load_env_file()
    fetch_videos()
