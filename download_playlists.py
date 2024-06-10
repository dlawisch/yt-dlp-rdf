import subprocess
import os
import json
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from xml.sax.saxutils import escape
from pathvalidate import sanitize_filename

def format_date(date_str):
    #print("Trying date", date_str)
    try:
        date_obj = datetime.strptime(date_str, '%Y%m%d')
        #print("Got", date_obj.strftime('%Y-%m-%d'))
        return date_obj.strftime('%Y-%m-%d')
    except ValueError:
        print("date problem")
        return datetime.now().strftime('%Y-%m-%d')

def extract_video_index(filename):
    match = re.match(r"(\d+)", filename)
    return int(match.group(1)) if match else None


def process_playlist(playlist_url, download_directory):
    # Run yt-dlp to download the playlist and export metadata
    subprocess.run(['yt-dlp', '--download-archive', '-N16', '--format', 'bv*[ext=mp4]', '-S', '+res:720,codec,br', '--embed-subs', '--embed-thumbnail', '--write-info-json', '--sponsorblock-mark', 'all', '--output', '%(playlist)s/%(playlist_index)s %(title)s.%(ext)s', playlist_url])

    # Parse playlist metadata
    playlist_info_json = None
    for filename in os.listdir(download_directory):
        if filename.endswith('.info.json') and int(filename.split(maxsplit=1)[0]) == 0:
            with open(os.path.join(download_directory, filename), 'r', encoding='utf-8') as f:
                playlist_info_json = json.load(f)

    if not playlist_info_json:
        raise FileNotFoundError("Playlist info JSON not found", download_directory)

    playlist_title = escape(playlist_info_json['title'])
    playlist_channel = escape(playlist_info_json['uploader'])
    playlist_id = playlist_info_json['id']
    playlist_description = playlist_info_json.get('description', '')
    playlist_date = format_date(playlist_info_json.get('modified_date', 'aaa'))

    # Start building the RDF content
    rdf_content = f'''<rdf:RDF
xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
xmlns:z="http://www.zotero.org/namespaces/export#"
xmlns:bib="http://purl.org/net/biblio#"
xmlns:foaf="http://xmlns.com/foaf/0.1/"
xmlns:dc="http://purl.org/dc/elements/1.1/"
xmlns:dcterms="http://purl.org/dc/terms/"
xmlns:prism="http://prismstandard.org/namespaces/1.2/basic/"
xmlns:link="http://purl.org/rss/1.0/modules/link/">
    <rdf:Description rdf:about="{playlist_url}">
        <z:itemType>dataset</z:itemType>
        <bib:authors>
            <rdf:Seq>
                <rdf:li>
                    <foaf:Person>
                       <foaf:surname>{playlist_channel}</foaf:surname>
                    </foaf:Person>
                </rdf:li>
            </rdf:Seq>
        </bib:authors>
        <dc:title>{playlist_title}</dc:title>
    <dc:date>{playlist_date}</dc:date>
        <dc:identifier>
            <dcterms:URI>
                <rdf:value>{playlist_url}</rdf:value>
            </dcterms:URI>
        </dc:identifier>
        <dcterms:dateSubmitted>{datetime.now().isoformat()}</dcterms:dateSubmitted>
        <z:type>Playlist</z:type>
        <prism:number>{playlist_id}</prism:number>
    </rdf:Description>'''

    video_index_total = sum(1 for filename in os.listdir(download_directory) if filename.endswith('.info.json')) - 1

    # Process each video metadata
    for filename in os.listdir(download_directory):
        if filename.endswith('.info.json'):
            video_index = extract_video_index(filename)
            # print(video_index)
            if video_index == 0:
                continue

            with open(os.path.join(download_directory, filename), 'r', encoding='utf-8') as f:
                video_info = json.load(f)

                video_title = escape(video_info['title'])
                video_description = video_info.get('description', '')
                video_date = format_date(video_info.get('upload_date', ''))
                video_duration = video_info.get('duration', 0)
                video_id = video_info['id']
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                video_file_mp4 = escape(filename.replace('.info.json', '.mp4'))

                rdf_content += f'''
                <bib:Recording rdf:about="{video_url}">
            <z:itemType>videoRecording</z:itemType>
            <dcterms:isPartOf>
                <bib:Series>
                    <dcterms:alternative>{playlist_title}</dcterms:alternative>
                </bib:Series>
            </dcterms:isPartOf>
            <z:directors>
                <rdf:Seq>
                    <rdf:li>
                        <foaf:Person>
                           <foaf:surname>{playlist_channel}</foaf:surname>
                        </foaf:Person>
                    </rdf:li>
                </rdf:Seq>
            </z:directors>
            <link:link rdf:resource="{video_id}"/>
            <dc:title>{video_index} {video_title}</dc:title>
            <dc:date>{video_date}</dc:date>
            <dc:identifier>
                <dcterms:URI>
                   <rdf:value>{video_url}</rdf:value>
                </dcterms:URI>
            </dc:identifier>
            <dcterms:dateSubmitted>{datetime.now().isoformat()}</dcterms:dateSubmitted>
            <prism:volume>{video_index}</prism:volume>
            <z:numberOfVolumes>{video_index_total}</z:numberOfVolumes>
            <z:runningTime>{video_duration // 60}:{video_duration % 60:02d}</z:runningTime>
        </bib:Recording>
        <z:Attachment rdf:about="{video_id}">
            <z:itemType>attachment</z:itemType>
            <rdf:resource>{video_file_mp4}</rdf:resource>
            <dc:title>{video_title}.mp4</dc:title>
            <dc:identifier>
                <dcterms:URI>
                   <rdf:value>{video_url}</rdf:value>
                </dcterms:URI>
            </dc:identifier>
            <dcterms:dateSubmitted>{datetime.now().isoformat()}</dcterms:dateSubmitted>
            <z:linkMode>1</z:linkMode>
            <link:type>video/mp4</link:type>
        </z:Attachment>'''

    rdf_content += '''
</rdf:RDF>
'''

    # Save RDF content to file
    rdf_file_path = os.path.join(download_directory, sanitize_filename(f'{playlist_title}.rdf'))
    with open(rdf_file_path, 'w', encoding='utf-8') as rdf_file:
        rdf_file.write(rdf_content)

    print(f'RDF file created: {rdf_file_path}')


def main():
    # Read playlist URLs from playlists.txt
    with open('playlists.txt', 'r') as file:
        playlist_urls = file.read().strip().split('\n')

    with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = []
        for playlist_url in playlist_urls:
            # Create a directory for each playlist
            playlist_id = playlist_url.split('list=')[-1]
            download_directory = os.path.join('downloads', playlist_id)
            os.makedirs(download_directory, exist_ok=True)

            # Submit each playlist processing task to the executor
            futures.append(executor.submit(process_playlist, playlist_url, download_directory))

        # Wait for all futures to complete
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f'Error: {e}')


if __name__ == '__main__':
    main()
