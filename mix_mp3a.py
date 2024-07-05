import os
import subprocess
import argparse
import json
from collections import namedtuple

Track = namedtuple('Track', ['path', 'name'])

def read_m3u_playlist(playlist_path):
    tracks = []
    with open(playlist_path, 'r') as file:
        for line in file:
            line = line.strip()
            if line and not line.startswith('#'):
                track_path = os.path.join(os.path.dirname(playlist_path), line)
                track_name = os.path.splitext(os.path.basename(line))[0]
                tracks.append(Track(track_path, track_name))
    return tracks

def generate_ffmpeg_command(tracks, output_file, crossfade_duration):
    inputs = [f"-i \"{track.path}\"" for track in tracks]
    filter_complex_parts = []
    last_output = f"[0:a]"

    for i in range(1, len(tracks)):
        current_output = f"[a{i}]"
        filter_complex_parts.append(
            f"{last_output}[{i}:a]acrossfade=d={crossfade_duration}:c1=tri:c2=tri{current_output};"
        )
        last_output = current_output

    filter_complex = "".join(filter_complex_parts).rstrip(';')

    command = f"ffmpeg {' '.join(inputs)} -filter_complex \"{filter_complex}\" -map \"{last_output}\" -c:a libmp3lame \"{output_file}\""
    return command

def get_audio_duration(file_path):
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', file_path]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    data = json.loads(result.stdout)
    return float(data['format']['duration'])

def generate_waveform_with_text(input_audio, output_video, background_png, tracks, visualization_type, wave_color, wave_opacity, text_color='orange', text_size=24):
    text_filters = []
    total_duration = 0
    for i, track in enumerate(tracks):
        escaped_name = track.name.replace("'", "'\\\\\\''")
        start_time = total_duration
        track_duration = get_audio_duration(track.path)
        end_time = start_time + track_duration
        text_filters.append(
            f"drawtext=fontsize={text_size}:fontcolor={text_color}:box=1:boxcolor=black@0.5:boxborderw=5:"
            f"x=10:y=h-th-10:text='{escaped_name}':enable='between(t,{start_time},{end_time})'"
        )
        total_duration += track_duration

    text_filters.append(
        f"drawtext=fontsize={text_size}:fontcolor={text_color}:box=1:boxcolor=black@0.5:boxborderw=5:"
        "x=w-tw-10:y=h-th-10:text='%{pts\\:hms}'"
    )
    
    text_filter_string = ','.join(text_filters)

    filter_complex = (
        f"[0:v]scale=1000:1000[bg];"
        f"[1:a]showwaves=s=1000x1000:mode={visualization_type}:colors={wave_color}@{wave_opacity}[waves];"
        f"[bg][waves]overlay=format=auto,format=yuv420p,{text_filter_string}[v]"
    )

    waveform_command = [
        "ffmpeg",
        "-loop", "1",
        "-i", background_png,
        "-i", input_audio,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "1:a",
        "-c:v", "libx264",
        "-c:a", "copy",
        "-t", str(total_duration),
        output_video,
        "-y"
    ]
    
    subprocess.run(waveform_command, check=True)

def main():
    parser = argparse.ArgumentParser(description="Połączenie plików MP3 z playlisty M3U w jeden plik z efektem crossfade, dodanie tła PNG, waveformy i napisów.")
    parser.add_argument("input_dir", type=str, help="Ścieżka do katalogu z plikami MP3 i playlistą M3U.")
    parser.add_argument("output_file", type=str, help="Nazwa pliku wyjściowego MP4 z efektem crossfade, tłem PNG i waveformą.")
    parser.add_argument("--crossfade_duration", type=int, default=5, help="Czas trwania crossfade w sekundach. Domyślnie 5 sekund.")
    parser.add_argument("--background_png", type=str, required=True, help="Ścieżka do pliku PNG używanego jako tło.")
    parser.add_argument("--visualization_type", type=str, default="line", choices=["line", "p2p", "cline"], 
                        help="Typ wizualizacji fali dźwiękowej. Opcje: line (linia), p2p (punkt do punktu), cline (kolorowa linia). Domyślnie: line.")
    parser.add_argument("--wave_color", type=str, default="white", help="Kolor fali dźwiękowej. Można użyć nazw kolorów (np. 'red', 'blue') lub kodów hex (np. '0xFFFFFF'). Domyślnie: white.")
    parser.add_argument("--wave_opacity", type=float, default=1.0, help="Przezroczystość fali dźwiękowej. Wartość od 0.0 (pełna przezroczystość) do 1.0 (brak przezroczystości). Domyślnie: 1.0.")
    parser.add_argument("--text_color", type=str, default="orange", help="Kolor tekstu na waveformie. Domyślnie: orange.")
    parser.add_argument("--text_size", type=int, default=24, help="Rozmiar czcionki tekstu na waveformie. Domyślnie: 24.")

    args = parser.parse_args()

    input_dir = args.input_dir
    output_file = args.output_file
    if not output_file.lower().endswith('.mp4'):
        output_file += '.mp4'
    crossfade_duration = args.crossfade_duration
    background_png = args.background_png
    visualization_type = args.visualization_type
    wave_color = args.wave_color
    wave_opacity = args.wave_opacity
    text_color = args.text_color
    text_size = args.text_size

    # Znajdź plik M3U w katalogu wejściowym
    m3u_files = [f for f in os.listdir(input_dir) if f.endswith('.m3u')]
    if not m3u_files:
        print("Nie znaleziono pliku M3U w katalogu wejściowym.")
        return
    
    playlist_path = os.path.join(input_dir, m3u_files[0])
    tracks = read_m3u_playlist(playlist_path)

    if len(tracks) < 2:
        print("Potrzebujesz przynajmniej dwóch plików mp3 w playliście, aby utworzyć mix.")
        return

    try:
        # Generowanie mixu audio
        ffmpeg_command = generate_ffmpeg_command(tracks, "temp_audio.mp3", crossfade_duration)
        print("Wykonywanie komendy generowania mixu audio:")
        print(ffmpeg_command)
        subprocess.run(ffmpeg_command, shell=True, check=True)
        
        print("Mix audio został wygenerowany pomyślnie.")

        # Generowanie waveformy dla mixu wideo z napisami
        input_audio = "temp_audio.mp3"
        print("Generowanie waveformy z napisami...")
        generate_waveform_with_text(input_audio, output_file, background_png, tracks, visualization_type, wave_color, wave_opacity, text_color=text_color, text_size=text_size)
        
        print(f"Waveforma z napisami została wygenerowana pomyślnie. Plik wyjściowy: {output_file}")

    except subprocess.CalledProcessError as e:
        print(f"Wystąpił błąd podczas przetwarzania: {e}")
        print(f"Komenda, która spowodowała błąd: {e.cmd}")
        print(f"Kod wyjścia: {e.returncode}")
        print(f"Wyjście: {e.output}")
    except Exception as e:
        print(f"Wystąpił nieoczekiwany błąd: {e}")
    finally:
        # Usuń tymczasowy plik audio, jeśli istnieje
        if os.path.exists("temp_audio.mp3"):
            os.remove("temp_audio.mp3")
            print("Usunięto tymczasowy plik audio.")

if __name__ == "__main__":
    main()
