"""
Audio Detection Utility Module
Provides functions for detecting and analyzing audio content in videos
"""

import os
import numpy as np
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip
import random

def detect_meaningful_audio(video_path, silence_threshold=-50, min_duration=1.0, sample_count=10):
    """
    Detect if video has meaningful audio (not just silent audio tracks)
    
    Args:
        video_path (str): Path to video file
        silence_threshold (float): dB threshold below which audio is considered silent
        min_duration (float): Minimum duration of non-silent audio required (seconds)
        sample_count (int): Number of sample points to check throughout video
    
    Returns:
        dict: {
            'has_audio_stream': bool,
            'has_meaningful_audio': bool,
            'audio_duration': float,
            'silent_duration': float,
            'non_silent_duration': float,
            'recommendation': str,  # 'add_music' or 'keep_original'
            'samples_analyzed': int,
            'analysis_method': str
        }
    """
    try:
        # Load video
        with VideoFileClip(video_path) as clip:
            # Check if audio track exists
            if clip.audio is None:
                return {
                    'has_audio_stream': False,
                    'has_meaningful_audio': False,
                    'audio_duration': 0,
                    'silent_duration': 0,
                    'non_silent_duration': 0,
                    'recommendation': 'add_music',
                    'samples_analyzed': 0,
                    'analysis_method': 'no_audio_track'
                }
            
            # Analyze audio content
            audio = clip.audio
            duration = audio.duration
            
            # Sample audio at multiple points to check for silence
            actual_sample_count = min(sample_count, int(duration))
            non_silent_duration = 0
            
            for i in range(actual_sample_count):
                start_time = (i / actual_sample_count) * duration
                sample_duration = min(1.0, duration - start_time)  # 1 second samples
                
                if sample_duration < 0.1:  # Skip very short samples
                    continue
                
                try:
                    # Extract audio sample
                    audio_sample = audio.subclip(start_time, start_time + sample_duration)
                    audio_array = audio_sample.to_soundarray()
                    
                    # Calculate RMS (Root Mean Square) to measure audio level
                    if len(audio_array.shape) > 1:
                        # Stereo - average both channels
                        rms = np.sqrt(np.mean(audio_array**2))
                    else:
                        # Mono
                        rms = np.sqrt(np.mean(audio_array**2))
                    
                    # Convert to dB
                    if rms > 0:
                        db_level = 20 * np.log10(rms)
                        if db_level > silence_threshold:
                            non_silent_duration += sample_duration
                    
                except Exception:
                    # Skip problematic samples
                    continue
            
            silent_duration = duration - non_silent_duration
            has_meaningful_audio = non_silent_duration >= min_duration
            
            # Determine recommendation
            if not has_meaningful_audio:
                if non_silent_duration > 0:
                    recommendation = 'add_music'  # Has some audio but mostly silent
                    analysis_method = 'mostly_silent'
                else:
                    recommendation = 'add_music'  # Completely silent
                    analysis_method = 'completely_silent'
            else:
                recommendation = 'keep_original'  # Has sufficient meaningful audio
                analysis_method = 'has_meaningful_audio'
            
            return {
                'has_audio_stream': True,
                'has_meaningful_audio': has_meaningful_audio,
                'audio_duration': duration,
                'silent_duration': silent_duration,
                'non_silent_duration': non_silent_duration,
                'recommendation': recommendation,
                'samples_analyzed': actual_sample_count,
                'analysis_method': analysis_method
            }
            
    except Exception as e:
        # Fallback - assume no meaningful audio on error
        return {
            'has_audio_stream': False,
            'has_meaningful_audio': False,
            'audio_duration': 0,
            'silent_duration': 0,
            'non_silent_duration': 0,
            'recommendation': 'add_music',
            'samples_analyzed': 0,
            'analysis_method': 'error',
            'error': str(e)
        }

def should_add_music(video_path, profile):
    """
    Determine if music should be added to this video based on profile settings
    
    Args:
        video_path (str): Path to video file
        profile (dict): Profile configuration with music settings
    
    Returns:
        tuple: (should_add: bool, reason: str)
    """
    music_mode = profile.get('music_mode', 'smart')
    
    if music_mode == 'disabled':
        return False, "Music disabled in profile settings"
    elif music_mode == 'always':
        return True, "Always add music mode enabled"
    elif music_mode == 'smart':
        # Analyze the video audio with optimal settings
        silence_threshold = -45.0  # Good balance for most content
        audio_analysis = detect_meaningful_audio(video_path, silence_threshold)
        
        if audio_analysis['recommendation'] == 'add_music':
            if not audio_analysis['has_audio_stream']:
                return True, "No audio track detected"
            else:
                return True, f"Audio track is mostly silent ({audio_analysis['silent_duration']:.1f}s of {audio_analysis['audio_duration']:.1f}s silent)"
        else:
            return False, f"Meaningful audio detected ({audio_analysis['non_silent_duration']:.1f}s of meaningful audio)"
    else:
        return False, "Unknown music mode"

def get_random_music_file(music_dir):
    """
    Get a random music file from the music directory
    
    Args:
        music_dir (str): Path to music directory
        
    Returns:
        str or None: Path to random music file, or None if no files found
    """
    if not os.path.exists(music_dir):
        return None
    
    # Common audio file extensions
    audio_extensions = {'.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac'}
    
    music_files = []
    
    # Check subdirectories too (like exciting/, scary/, etc.)
    for root, dirs, files in os.walk(music_dir):
        for file in files:
            if any(file.lower().endswith(ext) for ext in audio_extensions):
                music_files.append(os.path.join(root, file))
    
    if not music_files:
        return None
    
    return random.choice(music_files)

def add_background_music(video_path, music_path, output_path, volume=0.3):
    """
    Add background music to a video
    
    Args:
        video_path (str): Path to input video
        music_path (str): Path to music file
        output_path (str): Path for output video
        volume (float): Music volume (0.0 to 1.0)
        
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        with VideoFileClip(video_path) as video:
            with AudioFileClip(music_path) as music:
                # Loop music to match video duration if needed
                if music.duration < video.duration:
                    # Calculate how many loops we need
                    loops_needed = int(video.duration / music.duration) + 1
                    music = music.loop(n=loops_needed)
                
                # Trim music to match video duration
                music = music.subclip(0, video.duration)
                
                # Adjust volume to optimal level
                music = music.volumex(volume)
                
                # Check if video already has audio
                if video.audio is not None:
                    # Combine existing audio with music (preserve original audio if any)
                    combined_audio = CompositeAudioClip([video.audio, music])
                else:
                    # Use music as the only audio track
                    combined_audio = music
                
                # Set the new audio to the video
                final_video = video.set_audio(combined_audio)
                
                # Write the result
                final_video.write_videofile(
                    output_path,
                    codec='libx264',
                    audio_codec='aac',
                    verbose=False,
                    logger=None
                )
                
                return True, f"Successfully added background music: {os.path.basename(music_path)}"
                
    except Exception as e:
        return False, f"Error adding background music: {str(e)}"

def process_video_with_audio_check(video_path, profile, log_callback=None):
    """
    Process video and add music if needed based on profile settings
    
    Args:
        video_path (str): Path to the video file
        profile (dict): Profile configuration
        log_callback (function): Optional function to call for logging
        
    Returns:
        str: Path to final processed video
    """
    def log(message):
        if log_callback:
            log_callback(message)
        else:
            print(message)
    
    music_mode = profile.get('music_mode', 'smart')
    music_dir = profile.get('music_dir', '')
    
    # Check if music processing is disabled
    if music_mode == 'disabled':
        log("🎵 Music processing disabled for this channel")
        return video_path  # Return original video without music processing
    
    # Check if we should add music
    should_add_music_flag, music_reason = should_add_music(video_path, profile)
    
    if should_add_music_flag:
        if not music_dir or not os.path.exists(music_dir):
            log(f"⚠️ Cannot add music: Music directory not found or not set ({music_dir})")
            return video_path
        
        # Get random music file
        music_file = get_random_music_file(music_dir)
        if not music_file:
            log(f"⚠️ Cannot add music: No music files found in {music_dir}")
            return video_path
        
        log(f"🎵 {music_reason}")
        log(f"🎵 Selected music: {os.path.basename(music_file)}")
        
        # Create output path for video with music
        base_name = os.path.splitext(video_path)[0]
        output_path = f"{base_name}_with_music.mp4"
        
        # Add background music with volume from profile
        music_volume = profile.get('music_volume', 0.3)  # Use profile setting, default to 30%
        success, message = add_background_music(video_path, music_file, output_path, volume=music_volume)
        
        if success:
            log(f"✅ {message}")
            # Clean up original file if music was added successfully
            try:
                os.remove(video_path)
            except:
                pass
            return output_path
        else:
            log(f"❌ {message}")
            return video_path
    else:
        log(f"🔊 {music_reason}")
        return video_path
