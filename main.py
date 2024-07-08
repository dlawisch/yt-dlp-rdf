import subprocess
import os
import json
import re
import argparse
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from xml.sax.saxutils import escape
from pathvalidate import sanitize_filename

def setup_logging(verbose):
    """
    Sets up logging configuration.
    """
    log_level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=log_level
    )

def format_date(date_str):
    """
    Formats the date string to 'YYYY-MM-DD' format.
    If parsing fails, returns the current date in 'YYYY-MM-DD' format.
    """
    try:
        date_obj = datetime.strptime(date_str, '%Y%m%d')
        return date_obj.strftime('%Y-%m-%d')
    except ValueError:
        logging.warning("Failed to parse date string '%s'. Using current date.", date_str)
        return datetime.now().strftime('%Y-%m-%d')

def extract_video_index(filename):
    """
    Extracts the video index from the filename using regex.
    Returns the index as an integer or None if no match is found.
    """
    match = re.match(r"(\d+)", filename)
    return int(match.group(1)) if match else None

def download_playlist(playlist_url, download_directory):
    """
    Downloads the playlist using yt-dlp and saves metadata files in the specified directory.
    """
    logging.info("Downloading playlist: %s", playlist_url)

    yt_dlp_command = ['yt-dlp','--format', 'bv*[ext=mp4]', '-S', '+res~540,codec,br', '-N8', '--write-auto-sub', '--embed-subs', '--convert-thumbnails', 'jpg', '--embed-thumbnail', '--write-info-json', '--sponsorblock-mark', 'all', '--quiet', '--verbose', '--download-archive',  f'{download_directory}/archive.txt' , '--output', f'{download_directory}/%(playlist)s/%(playlist_index)s %(title)s.%(ext)s', playlist_url]
    logging.info(' '.join(yt_dlp_command))
    result = subprocess.run(
        yt_dlp_command,
        text=True
    )
    if result.returncode == 0:
        logging.info("Successfully downloaded playlist: %s", playlist_url)
    else:
        logging.error("Error downloading playlist: %s\n%s", playlist_url, result.stderr)
    logging.debug("yt-dlp output:\n%s", result.stdout)

def generate_rdf(playlist_url, download_directory):
    """
    Generates an RDF file for the downloaded playlist and saves it in the specified directory.
    """
    logging.info("Generating RDF for playlist: %s", playlist_url)

    playlist_info_json = None
    for filename in os.listdir(download_directory):
        if filename.endswith('.info.json') and int(filename.split(maxsplit=1)[0]) == 0:
            with open(os.path.join(download_directory, filename), 'r', encoding='utf-8') as f:
                playlist_info_json = json.load(f)
                logging.debug("Loaded playlist metadata from %s", filename)

    if not playlist_info_json:
        raise FileNotFoundError("Playlist info JSON not found", download_directory)

    playlist_title = escape(playlist_info_json['title'])
    playlist_channel = escape(playlist_info_json['uploader'])
    playlist_id = playlist_info_json['id']
    playlist_description = playlist_info_json.get('description', '')
    playlist_date = format_date(playlist_info_json.get('modified_date', 'aaa'))

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

    for filename in os.listdir(download_directory):
        if filename.endswith('.info.json'):
            video_index = extract_video_index(filename)
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

    rdf_file_path = os.path.join(download_directory, sanitize_filename(f'{playlist_title}.rdf'))
    with open(rdf_file_path, 'w', encoding='utf-8') as rdf_file:
        rdf_file.write(rdf_content)

    logging.info('RDF file created: %s', rdf_file_path)

def main():
    parser = argparse.ArgumentParser(description="Download YouTube playlists and generate Zotero RDF files.")
    parser.add_argument('playlists_file', type=str, help="Path to the file containing playlist URLs.")
    parser.add_argument('--download-only', action='store_true', help="Only download the playlists.")
    parser.add_argument('--rdf-only', action='store_true', help="Only generate RDF files for already downloaded playlists.")
    parser.add_argument('--download-path', type=str, default='downloads', help="Path to the download directory.")
    parser.add_argument('--verbose', action='store_true', help="Enable detailed logging.")

    args = parser.parse_args()
    setup_logging(args.verbose)

    with open(args.playlists_file, 'r') as file:
        playlist_urls = file.read().strip().split('\n')

    download_directory = os.path.realpath(args.download_path)
    os.makedirs(download_directory, exist_ok=True)

    with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = []
        for playlist_url in playlist_urls:
            playlist_id = playlist_url.split('list=')[-1]

            if args.download_only:
                futures.append(executor.submit(download_playlist, playlist_url, download_directory))
            elif args.rdf_only:
                futures.append(executor.submit(generate_rdf, playlist_url, download_directory))
            else:
                futures.append(executor.submit(download_playlist, playlist_url, download_directory))
                futures.append(executor.submit(generate_rdf, playlist_url, download_directory))

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error('Error: %s', e)

if __name__ == '__main__':
    main()
