#!/usr/bin/env python3
"""
YouTube‑Shorts bot – Multi-Channel Processor
─────────────────────────────────────────────────────
• Processes videos for multiple channels based on profiles.json.
• Maintains the same functionality as individual scripts.
• Dynamically loads channel-specific configurations.
"""

import os, sys, json, uuid, random, logging, tempfile, traceback, re, warnings
from datetime import datetime, timedelta
import socket
import time
import locale

# Import our audio detection module
try:
    from audio_detection import process_video_with_audio_check
except ImportError:
    print("⚠️ Audio detection module not found. Music features will be limited.")
    process_video_with_audio_check = None

# Set up UTF-8 encoding for the entire process
if sys.platform.startswith('win'):
    # On Windows, ensure UTF-8 encoding
    try:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except locale.Error:
        try:
            locale.setlocale(locale.LC_ALL, 'C.UTF-8')
        except locale.Error:
            pass  # Use system default

# Set environment variables for UTF-8 handling
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'

# Monkey patch to handle byte 0x80 and similar UTF-8 errors at the HTTP response level
import requests.models
original_text_property = requests.models.Response.text

@property
def safe_text_property(self):
    """Safer version of Response.text that handles byte 0x80 and similar UTF-8 errors"""
    try:
        return original_text_property.fget(self)
    except UnicodeDecodeError as e:
        # Handle specific UTF-8 errors like byte 0x80
        if hasattr(self, 'content') and self.content:
            try:
                # Try with surrogateescape to handle invalid bytes
                return self.content.decode('utf-8', errors='surrogateescape')
            except UnicodeDecodeError:
                # Try with other common encodings
                for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                    try:
                        return self.content.decode(encoding, errors='replace')
                    except (UnicodeDecodeError, LookupError):
                        continue
                # Final fallback
                return self.content.decode('utf-8', errors='replace')
        return ""

# Apply the monkey patch
requests.models.Response.text = safe_text_property

# Suppress MoviePy warnings
warnings.filterwarnings("ignore", category=UserWarning, module="moviepy")

# ── paths ───────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILES_FILE = os.path.join(BASE_DIR, "profiles.json")
TOKENS_DIR = os.path.join(BASE_DIR, "tokens")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")
OUT_DIR = os.path.join(BASE_DIR, "out")

# Create necessary directories
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(TOKENS_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

# ── Pillow ANTIALIAS patch for 3.12+ ────────────────────────────────────
import PIL, PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

import pytz, yt_dlp, praw, numpy as np
from PIL import ImageDraw, ImageFont
from moviepy.editor import (
    VideoFileClip, AudioFileClip, CompositeVideoClip,
    CompositeAudioClip, afx
)
from moviepy.video.VideoClip import ImageClip
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient import errors as googleapiclient_errors
import config

# ── constants / settings ────────────────────────────────────────────────
TZ = pytz.timezone("America/New_York")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
FONT_SIZE = 70
CAPTION_Y = 280  # Default text position (can be overridden by profile config, new default is 320)
CAPTION_MAX = 60
MAX_DURATION = 60
MAX_REDDIT_ID = 5_000

# Bad words for censoring
BAD_WORDS = frozenset(["fuck","shit","bitch","asshole","dick","bastard","damn"])
_bad_re = re.compile(r'\b(' + "|".join(map(re.escape, BAD_WORDS)) + r')\b', re.I)

def load_profiles():
    try:
        with open(PROFILES_FILE, "r", encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Failed to load profiles: {e}")
        sys.exit(1)

def wait_for_internet_connection():
    while True:
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            return
        except OSError:
            print("No internet connection. Retrying in 5 seconds...")
            time.sleep(5)

# ── helpers from original scripts ─────────────────────────────────────

def _reddit_duration(p):
    """Get duration of reddit video - handles both PRAW and SafePost objects"""
    try:
        if hasattr(p, 'media') and p.media:
            if isinstance(p.media, dict) and "reddit_video" in p.media:
                return p.media["reddit_video"]["duration"]
        # Fallback for other formats
        return 0
    except Exception:
        return 0

def safe_get_post_attribute(post, attr_name, default=""):
    """Safely get a post attribute with comprehensive encoding error handling for byte 0x80 and similar issues"""
    try:
        # First, handle the special case where getting the attribute itself causes UTF-8 errors
        value = None
        try:
            # Try direct attribute access
            value = getattr(post, attr_name, None)
        except (UnicodeDecodeError, UnicodeEncodeError) as e:
            # If direct access fails due to encoding, try alternative methods
            print(f"  🔧 Direct attribute access failed for {attr_name} due to encoding: {e}")
            value = None
        except Exception as e:
            print(f"  🔧 Direct attribute access failed for {attr_name}: {e}")
            value = None
        
        # If direct access failed, try fallback methods
        if value is None:
            try:
                # Method 1: Try accessing via __dict__ with robust byte handling
                if hasattr(post, '__dict__') and attr_name in post.__dict__:
                    raw_value = post.__dict__[attr_name]
                    
                    # Handle different data types with specific focus on byte 0x80 issues
                    if isinstance(raw_value, bytes):
                        # Use surrogateescape to handle invalid UTF-8 bytes like 0x80
                        try:
                            # First try strict UTF-8
                            value = raw_value.decode('utf-8')
                        except UnicodeDecodeError:
                            # If that fails, use surrogateescape which converts problematic bytes to surrogates
                            try:
                                value = raw_value.decode('utf-8', errors='surrogateescape')
                                print(f"  🔧 Used surrogateescape for {attr_name}")
                            except UnicodeDecodeError:
                                # If even surrogateescape fails, try other common encodings
                                for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                                    try:
                                        value = raw_value.decode(encoding, errors='replace')
                                        print(f"  🔧 Used {encoding} encoding for {attr_name}")
                                        break
                                    except (UnicodeDecodeError, LookupError):
                                        continue
                                else:
                                    # Ultimate fallback: convert problematic bytes to safe representation
                                    safe_chars = []
                                    for byte in raw_value[:500]:  # Limit to first 500 bytes
                                        if 32 <= byte <= 126:  # Printable ASCII
                                            safe_chars.append(chr(byte))
                                        elif byte in [9, 10, 13]:  # Tab, newline, carriage return
                                            safe_chars.append(' ')
                                        else:
                                            # Replace problematic bytes (like 0x80) with safe placeholder
                                            safe_chars.append('?')
                                    value = ''.join(safe_chars).strip() or f"Post {attr_name} with encoding issues"
                    else:
                        value = raw_value
                
                # Method 2: Try _fetch_info if available
                elif hasattr(post, '_fetch_info') and attr_name in post._fetch_info:
                    value = post._fetch_info[attr_name]
                
                # Method 3: For Reddit posts, try to access the underlying JSON data
                elif hasattr(post, '_reddit') and hasattr(post, 'id'):
                    # This is a fallback that just returns a safe default
                    if hasattr(post, '_fetched') and post._fetched:
                        value = f"Post content with encoding issues ({attr_name})"
                    else:
                        value = None
                        
            except Exception as e:
                print(f"  🔧 Fallback access failed for {attr_name}: {e}")
                value = None
        
        # If we still don't have a value, use default
        if value is None:
            return str(default) if default else ""
        
        # Now handle the value we got with focus on byte 0x80 issues
        try:
            # Handle bytes specifically with surrogateescape
            if isinstance(value, bytes):
                # Use surrogateescape which is designed for this exact problem
                try:
                    value = value.decode('utf-8', errors='surrogateescape')
                except UnicodeDecodeError:
                    # If even surrogateescape fails, try other encodings
                    for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                        try:
                            value = value.decode(encoding, errors='replace')
                            break
                        except (UnicodeDecodeError, LookupError):
                            continue
                    else:
                        # Final fallback for bytes
                        value = repr(value)[2:-1]  # Convert to string representation without b' '
            
            # Convert to string and sanitize, handling surrogate characters
            str_value = str(value) if value is not None else str(default)
            
            # Special handling for numeric attributes
            if attr_name == 'score':
                try:
                    # For score, always return an integer
                    if isinstance(value, (int, float)):
                        return int(value)
                    else:
                        return int(str_value) if str_value.isdigit() or (str_value.startswith('-') and str_value[1:].isdigit()) else int(default) if isinstance(default, (int, float)) else 0
                except (ValueError, TypeError):
                    return int(default) if isinstance(default, (int, float)) else 0
            
            # Handle surrogates from surrogateescape and other problematic characters
            try:
                # Test if string can be encoded properly
                str_value.encode('utf-8')
                return sanitize_text_for_utf8(str_value)
            except UnicodeEncodeError:
                # Handle surrogate characters and other encoding issues
                cleaned_chars = []
                for char in str_value:
                    try:
                        char.encode('utf-8')
                        cleaned_chars.append(char)
                    except UnicodeEncodeError:
                        # Replace problematic characters (including surrogates) with safe alternatives
                        if ord(char) >= 0xDC80 and ord(char) <= 0xDCFF:
                            # This is a surrogate from surrogateescape - convert back to original byte representation
                            original_byte = ord(char) - 0xDC80
                            if 32 <= original_byte <= 126:
                                cleaned_chars.append(chr(original_byte))
                            else:
                                cleaned_chars.append('?')
                        else:
                            cleaned_chars.append('?')
                
                cleaned_value = ''.join(cleaned_chars).strip()
                return sanitize_text_for_utf8(cleaned_value) if cleaned_value else str(default)
            
        except (UnicodeDecodeError, UnicodeEncodeError) as e:
            print(f"  🔧 String conversion failed for {attr_name}: {e}")
            # Final fallback - return a safe default
            return f"Content with encoding issues" if not default else str(default)
            
    except Exception as e:
        print(f"  🔧 Complete failure accessing {attr_name}: {e}")
        return str(default) if default else ""

def safe_reddit_fetch(reddit, subreddit, sort_method="hot", timeframe="all", limit=50):
    """Safely fetch Reddit posts with comprehensive UTF-8 error handling"""
    try:
        # Get the subreddit object
        sub = reddit.subreddit(subreddit)
        
        # Fetch posts with error handling
        posts = []
        try:
            # Set up encoding handling for PRAW requests
            import requests
            import urllib3
            
            # Force UTF-8 for HTTP responses
            original_response_init = requests.Response.__init__
            
            def patched_response_init(self, *args, **kwargs):
                result = original_response_init(self, *args, **kwargs)
                if hasattr(self, 'encoding') and self.encoding is None:
                    self.encoding = 'utf-8'
                return result
            
            # Temporarily patch the Response init
            requests.Response.__init__ = patched_response_init
            
            try:
                # Choose the appropriate sorting method
                if sort_method == "hot":
                    raw_posts = sub.hot(limit=limit)
                elif sort_method == "new":
                    raw_posts = sub.new(limit=limit)
                elif sort_method.startswith("top_"):
                    # Extract timeframe from sort_method (e.g., "top_month" -> "month")
                    time_filter = sort_method[4:]  # Remove "top_" prefix
                    raw_posts = sub.top(time_filter=time_filter, limit=limit)
                else:
                    # Default to hot if unknown method
                    raw_posts = sub.hot(limit=limit)
                
                for i, post in enumerate(raw_posts):
                    try:
                        # Use safe attribute access to avoid encoding errors
                        post_id = safe_get_post_attribute(post, 'id', f'unknown_{i}')
                        score = safe_get_post_attribute(post, 'score', 0)
                        is_video = getattr(post, 'is_video', False) if hasattr(post, 'is_video') else False
                        
                        # Try to safely access text properties using our safe function
                        title = safe_get_post_attribute(post, 'title', '')
                        url = safe_get_post_attribute(post, 'url', '')
                        
                        if title and url:  # Only include posts with valid text data
                            posts.append(post)
                        else:
                            print(f"  ⚠️ Skipping post {i+1} due to empty title/URL after sanitization")
                            add_to_processed_list(post_id, "Empty title/URL after sanitization", subreddit)
                            
                    except (UnicodeDecodeError, UnicodeEncodeError) as ue:
                        post_id = safe_get_post_attribute(post, 'id', f'post_{i+1}')
                        print(f"  ⚠️ Skipping post {i+1} (ID: {post_id}) due to UTF-8 encoding error: {ue}")
                        print("UTF-8 error encountered: 'utf-8' codec can't decode byte 0x80 in position 0: invalid start byte")
                        print("The problematic post will be automatically skipped and marked as processed.")
                        # Add this problematic post to the "done" list so we don't try it again
                        add_to_processed_list(post_id, f"UTF-8 encoding error: {str(ue)}", subreddit)
                        continue
                    except Exception as e:
                        post_id = safe_get_post_attribute(post, 'id', f'post_{i+1}')
                        print(f"  ⚠️ Skipping post {i+1} (ID: {post_id}) due to error: {e}")
                        # Add this problematic post to the "done" list so we don't try it again
                        add_to_processed_list(post_id, f"Access error: {str(e)}", subreddit)
                        continue
            finally:
                # Restore original Response.__init__
                requests.Response.__init__ = original_response_init
        
        except (UnicodeDecodeError, UnicodeEncodeError) as ue:
            print(f"  ⚠️ UTF-8 error while fetching posts from Reddit API: {ue}")
            print("UTF-8 error encountered: 'utf-8' codec can't decode byte 0x80 in position 0: invalid start byte")
            print("The problematic post will be automatically skipped and marked as processed.")
            # Try to continue with what we have
            print(f"  🔄 Continuing with {len(posts)} successfully fetched posts...")
        
        return posts
    except Exception as e:
        print(f"Error during safe Reddit fetch: {e}")
        import traceback
        traceback.print_exc()
        return []

def add_to_processed_list(post_id, reason, subreddit):
    """Add a problematic post to the processed list so we don't try it again"""
    try:
        processed_file = os.path.join(PROCESSED_DIR, f"processed_skipped_{subreddit}.json")
        
        # Load existing skipped posts
        skipped_posts = []
        if os.path.exists(processed_file):
            try:
                with open(processed_file, 'r', encoding='utf-8') as f:
                    skipped_posts = json.load(f)
            except:
                skipped_posts = []
        
        # Add new skipped post
        skip_record = {
            "id": post_id,
            "reason": reason,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "subreddit": subreddit
        }
        skipped_posts.append(skip_record)
        
        # Save updated list
        with open(processed_file, 'w', encoding='utf-8') as f:
            json.dump(skipped_posts, f, indent=2, ensure_ascii=False)
        
        print(f"  📝 Marked post {post_id} as skipped due to: {reason}")
    except Exception as e:
        print(f"  ⚠️ Could not save skipped post record: {e}")

def cleanup_old_skipped_posts(subreddit, days_old=30):
    """Clean up skipped posts older than specified days to prevent file bloat"""
    try:
        processed_file = os.path.join(PROCESSED_DIR, f"processed_skipped_{subreddit}.json")
        if not os.path.exists(processed_file):
            return
        
        with open(processed_file, 'r', encoding='utf-8') as f:
            skipped_posts = json.load(f)
        
        # Filter out old posts
        cutoff_date = datetime.now() - timedelta(days=days_old)
        filtered_posts = []
        
        for post in skipped_posts:
            try:
                post_date = datetime.strptime(post.get('date', ''), "%Y-%m-%d %H:%M:%S")
                if post_date > cutoff_date:
                    filtered_posts.append(post)
            except:
                # Keep posts with invalid dates (safer)
                filtered_posts.append(post)
        
        # Save cleaned list
        if len(filtered_posts) < len(skipped_posts):
            with open(processed_file, 'w', encoding='utf-8') as f:
                json.dump(filtered_posts, f, indent=2, ensure_ascii=False)
            removed = len(skipped_posts) - len(filtered_posts)
            print(f"🧹 Cleaned up {removed} old skipped posts (older than {days_old} days)")
    except Exception as e:
        print(f"⚠️ Could not clean up skipped posts: {e}")

def load_skipped_posts(subreddit):
    """Load the list of posts we've already skipped due to problems"""
    try:
        # Clean up old skipped posts first (optional)
        cleanup_old_skipped_posts(subreddit)
        
        processed_file = os.path.join(PROCESSED_DIR, f"processed_skipped_{subreddit}.json")
        if os.path.exists(processed_file):
            with open(processed_file, 'r', encoding='utf-8') as f:
                skipped_posts = json.load(f)
                return {post["id"] for post in skipped_posts}
    except:
        pass
    return set()

def ultra_safe_reddit_fetch(reddit, subreddit, timeframe, limit, sort_method='top'):
    """Ultra-safe Reddit fetch with multiple fallback strategies for encoding issues"""
    print(f"🔍 Fetching posts from r/{subreddit}")
    
    # Try normal safe fetch first
    try:
        posts = safe_reddit_fetch(reddit, subreddit, sort_method, timeframe, limit)
        if posts:
            print(f"✅ Successfully fetched {len(posts)} posts from r/{subreddit}")
            return posts
    except Exception as e:
        print(f"⚠️ Primary fetch failed, trying alternative method: {e}")
    
    # Fallback: Use requests directly to bypass PRAW's encoding
    try:
        print("🔄 Using direct API requests as fallback")
        import requests
        import json as json_lib
        
        # Get Reddit OAuth token (if available)
        headers = {
            'User-Agent': config.REDDIT_USER_AGENT,
            'Accept': 'application/json',
            'Accept-Charset': 'utf-8'
        }
        
        # Determine the URL based on sort method
        if sort_method == 'new':
            url = f"https://www.reddit.com/r/{subreddit}/new.json"
            params = {
                'limit': min(limit, 25),  # Limit to avoid rate limiting
                'raw_json': 1  # Get raw JSON without HTML entities
            }
        elif sort_method == 'hot':
            url = f"https://www.reddit.com/r/{subreddit}/hot.json"
            params = {
                'limit': min(limit, 25),  # Limit to avoid rate limiting
                'raw_json': 1  # Get raw JSON without HTML entities
            }
        else:  # top variants
            url = f"https://www.reddit.com/r/{subreddit}/top.json"
            # Map our sort methods to Reddit timeframes
            timeframe_map = {
                'top_all': 'all',
                'top_year': 'year', 
                'top_month': 'month',
                'top': timeframe  # fallback to passed timeframe
            }
            reddit_timeframe = timeframe_map.get(sort_method, timeframe)
            params = {
                't': reddit_timeframe,
                'limit': min(limit, 25),  # Limit to avoid rate limiting
                'raw_json': 1  # Get raw JSON without HTML entities
            }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.encoding = 'utf-8'  # Force UTF-8 encoding
        
        if response.status_code == 200:
            data = response.json()
            posts = []
            
            for i, post_data in enumerate(data['data']['children']):
                try:
                    post_info = post_data['data']
                    
                    # Check if it's a video post
                    is_video = post_info.get('is_video', False)
                    if not is_video:
                        continue
                    
                    # Create a simple post object with safe attributes
                    class SafePost:
                        def __init__(self, data):
                            self.id = sanitize_text_for_utf8(str(data.get('id', f'unknown_{i}')))
                            self.title = sanitize_text_for_utf8(str(data.get('title', '')))
                            self.url = sanitize_text_for_utf8(str(data.get('url', '')))
                            self.score = int(data.get('score', 0))
                            self.is_video = data.get('is_video', False)
                            
                            # Handle duration safely
                            try:
                                if 'media' in data and data['media'] and 'reddit_video' in data['media']:
                                    self.media = {"reddit_video": {"duration": int(data['media']['reddit_video'].get('duration', 0))}}
                                else:
                                    self.media = None
                            except:
                                self.media = None
                    
                    safe_post = SafePost(post_info)
                    
                    # Validate the post has good data
                    if safe_post.title and safe_post.url and safe_post.id != f'unknown_{i}':
                        posts.append(safe_post)
                        print(f"  ✓ Direct API post {i+1}: {safe_post.title[:50]}...")
                    
                except Exception as e:
                    print(f"  ⚠️ Skipping direct API post {i+1}: {e}")
                    continue
            
            if posts:
                print(f"✅ Backup method succeeded: {len(posts)} posts")
                return posts
                
    except Exception as e:
        print(f"⚠️ Backup method also failed: {e}")
    
    # Return empty list and log the issue
    print("❌ All fetch methods failed - no posts retrieved")
    return []

def fetch_candidates(reddit, subreddit, done_ids, limit=40, safe_mode=False, sort_method='top_month', fallback_chain=None):
    """Fetch video candidates using sort method with fallback chain"""
    # Default fallback chain if none provided
    if fallback_chain is None:
        fallback_chain = ['top_month', 'top_year', 'top_all']
    
    # Load skipped posts so we don't try them again
    skipped_ids = load_skipped_posts(subreddit)
    all_done_ids = done_ids.union(skipped_ids)
    
    # Don't print excluded counts to terminal (already shown in GUI)
    
    # Try each sort method in the fallback chain
    for current_sort in fallback_chain:
        print(f"Searching using {current_sort} method...")
        try:
            # Determine timeframe for ultra_safe_reddit_fetch
            if current_sort == 'new':
                timeframe = 'all'  # For new posts, timeframe doesn't matter
            elif current_sort == 'hot':
                timeframe = 'all'  # For hot posts, timeframe doesn't matter
            elif current_sort == 'top_month':
                timeframe = 'month'
            elif current_sort == 'top_year':
                timeframe = 'year'
            elif current_sort == 'top_all':
                timeframe = 'all'
            else:
                timeframe = 'month'  # default
            
            # Adjust limit in safe mode
            current_limit = min(limit, 20) if safe_mode else limit
            
            # Use ultra-safe fetch as primary method
            all_posts = ultra_safe_reddit_fetch(reddit, subreddit, timeframe, current_limit, current_sort)
            # Don't print retrieved count to terminal (already shown in GUI)
            vids = []
            for i, p in enumerate(all_posts):
                try:
                    # Use safe attribute access to get post ID first - handle both PRAW and SafePost objects
                    if hasattr(p, 'id'):
                        post_id = sanitize_text_for_utf8(str(p.id))
                    else:
                        post_id = safe_get_post_attribute(p, 'id', f'unknown_{i}')
                    
                    # Check if post is already processed or skipped
                    if post_id in all_done_ids:
                        continue  # Skip already processed posts
                    
                    # Check post validity with UTF-8 safe handling
                    is_video = getattr(p, 'is_video', False) if hasattr(p, 'is_video') else False
                    duration = _reddit_duration(p)
                    
                    if (is_video and duration <= MAX_DURATION and duration > 0):
                        
                        # Test if we can safely access post data using our safe functions
                        try:
                            if hasattr(p, 'title') and hasattr(p, 'url'):
                                # SafePost or already safe object
                                safe_title = sanitize_text_for_utf8(str(p.title))
                                safe_url = sanitize_text_for_utf8(str(p.url))
                            else:
                                # PRAW object - use safe attribute access
                                safe_title = safe_get_post_attribute(p, 'title', '')
                                safe_url = safe_get_post_attribute(p, 'url', '')
                                
                            if safe_title and safe_url:
                                vids.append(p)
                            else:
                                add_to_processed_list(post_id, "Empty title/URL after sanitization", subreddit)
                        except (UnicodeDecodeError, UnicodeEncodeError) as ue:
                            add_to_processed_list(post_id, f"UTF-8 encoding error", subreddit)
                            continue
                        
                except (UnicodeDecodeError, UnicodeEncodeError, AttributeError) as e:
                    post_id = sanitize_text_for_utf8(str(getattr(p, 'id', f'unknown_{i}')))
                    add_to_processed_list(post_id, f"Encoding error", subreddit)
                    continue
                except Exception as e:
                    post_id = sanitize_text_for_utf8(str(getattr(p, 'id', f'unknown_{i}')))
                    add_to_processed_list(post_id, f"Processing error", subreddit)
                    continue
            
            if vids:
                # Sort by score - handle both PRAW and SafePost objects
                try:
                    if current_sort == 'new':
                        # For 'new', keep chronological order (don't sort by score)
                        sorted_vids = vids
                    else:
                        # For all other methods, sort by score (ensure score is int for comparison)
                        def get_safe_score(post):
                            try:
                                score = getattr(post, 'score', 0)
                                return int(score) if score is not None else 0
                            except (ValueError, TypeError):
                                return 0
                        sorted_vids = sorted(vids, key=get_safe_score, reverse=True)
                except:
                    sorted_vids = vids  # If sorting fails, use unsorted list
                print(f"Found {len(sorted_vids)} candidates using {current_sort}")
                return sorted_vids
        except (UnicodeDecodeError, UnicodeEncodeError) as ue:
            continue  # Try next sort method
        except Exception as e:
            print(f"Error fetching using {current_sort}: {e}")
            continue
    
    print("No candidates found with any sort method in fallback chain")
    return []

def dl_video(url, tmpl, abort_callback=None):
    """Download video using original script logic"""
    
    # Check for abort before starting download
    if abort_callback and abort_callback():
        raise Exception("Process aborted by user")
    
    class _QuietYT:
        def debug(self, msg): pass
        def info(self, msg): pass
        def warning(self, msg): pass
        def error(self, msg): pass

    opts = {
        "outtmpl": tmpl,
        "quiet": True,
        "no_warnings": True,
        "logger": _QuietYT(),
        "merge_output_format": "mp4",
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
    }
    
    # Check for abort before starting yt-dlp
    if abort_callback and abort_callback():
        raise Exception("Process aborted by user")
    
    # Use threading to make download interruptible
    import threading
    download_exception = None
    download_completed = threading.Event()
    
    def download_video():
        nonlocal download_exception
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as e:
            download_exception = e
        finally:
            download_completed.set()
    
    # Start download in background thread
    download_thread = threading.Thread(target=download_video, daemon=True)
    download_thread.start()
    
    # Check for abort every 0.5 seconds while downloading
    while download_thread.is_alive():
        if abort_callback and abort_callback():
            raise Exception("Process aborted by user")
        download_completed.wait(0.5)  # Check every 500ms
    
    # Check if download completed successfully
    if download_exception:
        raise Exception(f"Video download failed: {str(download_exception)}")
    
    # Check for abort after download completes
    if abort_callback and abort_callback():
        raise Exception("Process aborted by user")
    
    output_path = tmpl.replace("%(ext)s", "mp4")
    return output_path

def sanitize_text_for_utf8(txt):
    """Sanitize text to handle UTF-8 encoding issues, specifically targeting byte 0x80 and similar problems"""
    if not txt:
        return ""
    
    try:
        # First ensure it's a string
        if not isinstance(txt, str):
            txt = str(txt)
        
        # Handle the case where we might have binary data or mixed encodings
        if isinstance(txt, bytes):
            # Use surrogateescape for problematic bytes like 0x80
            try:
                txt = txt.decode('utf-8', errors='surrogateescape')
            except UnicodeDecodeError:
                # Try other common encodings that might handle byte 0x80
                for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                    try:
                        txt = txt.decode(encoding, errors='replace')
                        break
                    except (UnicodeDecodeError, LookupError):
                        continue
                else:
                    # Final fallback for bytes
                    txt = txt.decode('utf-8', errors='replace')
        
        # Now handle the string - test if it can be encoded/decoded properly
        try:
            # Test encoding to UTF-8 and back
            txt.encode('utf-8').decode('utf-8')
            return txt
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Handle encoding issues - this catches problematic characters including surrogates
            pass
        
    except Exception:
        # Convert to string if it's not already
        txt = str(txt) if txt is not None else ""
    
    # Robust fallback: handle any problematic characters including surrogates from surrogateescape
    try:
        # Method 1: Handle surrogate characters specifically (from surrogateescape)
        cleaned_chars = []
        for char in txt:
            try:
                # Test if character can be safely encoded
                char.encode('utf-8')
                cleaned_chars.append(char)
            except UnicodeEncodeError:
                # Handle surrogates and other problematic characters
                char_code = ord(char)
                if 0xDC80 <= char_code <= 0xDCFF:
                    # This is a surrogate from surrogateescape - convert back to original byte
                    original_byte = char_code - 0xDC80
                    if 32 <= original_byte <= 126:  # Printable ASCII
                        cleaned_chars.append(chr(original_byte))
                    elif original_byte in [9, 10, 13]:  # Tab, newline, carriage return
                        cleaned_chars.append(' ')
                    else:
                        # Replace problematic bytes (like 0x80) with space
                        cleaned_chars.append(' ')
                elif 32 <= char_code <= 126:  # Regular printable ASCII
                    cleaned_chars.append(char)
                elif char_code in [9, 10, 13]:  # Tab, newline, carriage return
                    cleaned_chars.append(' ')
                else:
                    # Replace other problematic characters
                    cleaned_chars.append(' ')
        
        safe_txt = ''.join(cleaned_chars).strip()
        
        # Method 2: If we still have issues or lost too much text, try encoding with replacement
        if not safe_txt or len(safe_txt) < 3:
            try:
                safe_txt = txt.encode('utf-8', errors='replace').decode('utf-8')
                # Remove replacement characters and clean up
                safe_txt = safe_txt.replace(' ', ' ')
                # Keep only printable characters and basic whitespace
                safe_txt = re.sub(r'[^\x20-\x7E\u00A0-\u024F\u1E00-\u1EFF]', ' ', safe_txt)
                safe_txt = re.sub(r'\s+', ' ', safe_txt).strip()
            except Exception:
                # If all else fails, keep only ASCII
                safe_txt = ''.join(char if ord(char) < 128 and char.isprintable() else ' ' for char in str(txt)).strip()
        
        return safe_txt if safe_txt else "Text with encoding issues"
        
    except Exception:
        # Final fallback: ASCII only with specific handling for common problematic bytes
        try:
            result_chars = []
            for char in str(txt):
                char_code = ord(char)
                if 32 <= char_code <= 126:  # Printable ASCII
                    result_chars.append(char)
                elif char_code in [9, 10, 13]:  # Tab, newline, carriage return
                    result_chars.append(' ')
                # Skip other characters (including byte 0x80 equivalents)
            
            result = ''.join(result_chars).strip()
            return result if result else "Content"
        except:
            return "Content"
        if ' ' in safe_txt:  # Unicode replacement character indicates issues
            # Remove emojis and special characters that cause issues
            # Keep only ASCII printable chars, basic Latin, and safe Unicode ranges
            safe_txt = re.sub(r'[^\x20-\x7E\u00A0-\u024F\u1E00-\u1EFF]', '', safe_txt)
            safe_txt = safe_txt.strip()
            
        return safe_txt if safe_txt else "Text with special characters"
        
    except Exception:
        # Final fallback: ASCII only
        try:
            return ''.join(char if ord(char) < 128 and char.isprintable() else '' for char in str(txt)).strip() or "Text content"
        except:
            return "Content"

def censor(txt):
    """Censor bad words from text with UTF-8 safe handling"""
    if not txt:
        return ""
    
    # Sanitize the text first
    safe_txt = sanitize_text_for_utf8(txt)
    
    try:
        return _bad_re.sub(lambda m: "*" * len(m.group()), safe_txt)
    except Exception:
        # If regex fails, return the sanitized text without censoring
        return safe_txt

def pick_music(music_dir):
    """Pick a random music file from directory"""
    if not music_dir or not os.path.exists(music_dir):
        return None
    pool = [f for f in os.listdir(music_dir) if f.lower().endswith((".mp3", ".m4a", ".wav"))]
    if pool:
        selected = random.choice(pool)
        return os.path.join(music_dir, selected)
    return None

def make_vertical_short(src, caption, out_fp, music_dir="", horizontal_zoom=1.6, font_config=None, music_volume=0.3, abort_callback=None):
    """Convert video to vertical YouTube Short format (1080x1920) with smart cropping"""
    print("🎬 Converting to YouTube Shorts format...")
    
    # Check for abort before starting
    if abort_callback and abort_callback():
        raise Exception("Process aborted by user")
    
    # Extract text position from font config early for cropping calculations
    text_position_y = CAPTION_Y  # Default
    if font_config and 'text_position_y' in font_config:
        text_position_y = font_config['text_position_y']
    print(f"📍 Text will be positioned at: {text_position_y} pixels from top")
    
    # Initialize all clips as None for proper cleanup
    clip = None
    vid = None
    txt_clip = None
    comp = None
    bg = None
    mfile = None

    try:
        # Load original video
        clip = VideoFileClip(src)
        
        # Check for abort after loading video
        if abort_callback and abort_callback():
            raise Exception("Process aborted by user")
        
        # Check if video is already vertical or needs conversion
        aspect_ratio = clip.w / clip.h
        
        if aspect_ratio <= (9/16):  # Already vertical or close to it
            print("📱 Video is already vertical, minimal processing...")
            # Just resize to fit YouTube Shorts dimensions
            if clip.h != 1920:
                vid = clip.resize(height=1920)
            else:
                vid = clip
            # Center horizontally if needed
            if vid.w != 1080:
                left = max(0, (vid.w - 1080) // 2)
                vid = vid.crop(x1=left, y1=0, x2=left + 1080, y2=1920)
        else:  # Horizontal video - smart crop with letterboxing
            print(f"📺 Horizontal video detected, applying {horizontal_zoom}x zoom crop...")
            print(f"📏 Original video size: {clip.w}x{clip.h}")
            
            # Apply configurable zoom factor for better framing
            target_width = int(1080 * horizontal_zoom)
            
            # Resize video with specified zoom - this works for any horizontal resolution
            resized_clip = clip.resize(width=target_width)
            new_height = resized_clip.h
            
            print(f"📏 Zoomed video size: {target_width}x{new_height} (target frame: 1080x1920)")
            
            # If the resized video is taller than 1920, we need to crop vertically
            if new_height > 1920:
                print("📏 Video too tall after scaling, cropping vertically...")
                # Calculate crop area to preserve content around text area
                text_area_height = text_position_y + 100  # Space for text
                
                # Try to keep the most important part (center-bottom for dashcam footage)
                crop_start = max(0, new_height - 1920)  # Start from bottom if possible
                crop_end = min(new_height, crop_start + 1920)
                
                # Adjust if we're cutting off too much from the top (where text goes)
                if crop_start > text_area_height:
                    crop_start = text_area_height
                    crop_end = crop_start + 1920
                
                # Crop the oversized video and center horizontally
                cropped_clip = resized_clip.crop(x1=0, y1=crop_start, x2=target_width, y2=crop_end)
                # Center the cropped video horizontally in 1080px frame
                vid = CompositeVideoClip([
                    cropped_clip.set_position(('center', 'center'))
                ], size=(1080, 1920), bg_color=(0, 0, 0))
            else:
                print(f"📱 Video fits with letterboxing, adding black bars (height: {new_height}px)")
                # Video is shorter than 1920px, so we can letterbox it
                # Center the zoomed video in the frame
                vid = CompositeVideoClip([
                    resized_clip.set_position(('center', 'center'))
                ], size=(1080, 1920), bg_color=(0, 0, 0))
        
        # Censor caption
        if caption:
            caption = censor(caption)
        
        # Check for abort before creating text overlay
        if abort_callback and abort_callback():
            raise Exception("Process aborted by user")
        
        # Create text overlay only if caption exists
        if caption:
            try:
                # Use font from profile config if available
                if font_config and 'path' in font_config:
                    font_path = font_config['path']
                    font_size = font_config.get('size', FONT_SIZE)
                else:
                    # Fallback to default Impact font
                    font_path = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'Fonts', 'impact.ttf')
                    font_size = FONT_SIZE
                
                print(f"🔤 Using font: {os.path.basename(font_path)} (size: {font_size})")
                font = ImageFont.truetype(font_path, font_size)
            except Exception as e:
                print(f"⚠️ Font loading failed ({e}), using default")
                font = ImageFont.load_default()
            
            # Calculate text dimensions
            tmp = PIL.Image.new("RGB", (1, 1))
            d = ImageDraw.Draw(tmp)
            bbox = d.textbbox((0, 0), caption.upper(), font=font, stroke_width=2)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            
            # Create text image with white text and black outline
            txt_img = PIL.Image.new("RGBA", (tw, th + 30), (255, 255, 255, 0))
            d2 = ImageDraw.Draw(txt_img)
            d2.text((0, 10), caption.upper(), font=font, fill="white", stroke_width=2, stroke_fill="black")
            
            # Create text clip
            txt_clip = ImageClip(np.array(txt_img)).set_duration(vid.duration)
            txt_clip = txt_clip.set_position(((vid.w - tw) // 2, text_position_y))
            
            # Create composite video with text overlay
            comp = CompositeVideoClip([vid, txt_clip])
        else:
            print("📝 No text overlay - using video without caption")
            # Use video without text overlay
            comp = vid
        
        # Add music if available
        mfile = pick_music(music_dir)
        if mfile:
            # Check for abort before processing music
            if abort_callback and abort_callback():
                raise Exception("Process aborted by user")
                
            print(f"🎵 Adding music: {os.path.basename(mfile)}")
            print(f"🔊 Music volume set to: {int(music_volume * 100)}%")
            
            bg = AudioFileClip(mfile).volumex(music_volume)
            
            # Loop or trim music to match video duration
            if bg.duration < comp.duration:
                bg = afx.audio_loop(bg, duration=comp.duration)
            else:
                bg = bg.subclip(0, comp.duration)
            
            # Mix with original audio or use as background
            if comp.audio:
                comp = comp.set_audio(CompositeAudioClip([comp.audio, bg]))
            else:
                comp = comp.set_audio(bg)
        else:
            print("🔇 No background music available")
        
        # Check for abort before the expensive video rendering operation
        if abort_callback and abort_callback():
            raise Exception("Process aborted by user")
        
        print("🎬 Rendering YouTube Short...")
        
        # Use threading to make video rendering interruptible
        import threading
        render_exception = None
        render_completed = threading.Event()
        
        def render_video():
            nonlocal render_exception
            try:
                comp.write_videofile(out_fp, fps=30, audio_codec="aac", remove_temp=True, verbose=False, logger=None)
            except Exception as e:
                render_exception = e
            finally:
                render_completed.set()
        
        # Start rendering in background thread
        render_thread = threading.Thread(target=render_video, daemon=True)
        render_thread.start()
        
        # Check for abort every 0.1 seconds while rendering
        while render_thread.is_alive():
            if abort_callback and abort_callback():
                raise Exception("Process aborted by user")
            render_completed.wait(0.1)  # Check every 100ms
        
        # Check if rendering completed successfully
        if render_exception:
            # If this is an abort, re-raise it
            if "Process aborted by user" in str(render_exception):
                raise render_exception
            # For other MoviePy errors, wrap them
            raise Exception(f"Video rendering failed: {str(render_exception)}")
        
        # Final abort check after rendering completes
        if abort_callback and abort_callback():
            raise Exception("Process aborted by user")
        
        print("✅ Video rendering completed successfully")
        return os.path.basename(mfile) if mfile else None

    finally:
        # Clean up all moviepy resources
        def safe_close(clip_obj):
            if clip_obj is not None:
                try:
                    if hasattr(clip_obj, 'audio') and clip_obj.audio is not None:
                        clip_obj.audio.close()
                    if hasattr(clip_obj, 'reader') and clip_obj.reader is not None:
                        clip_obj.reader.close()
                    clip_obj.close()
                except Exception:
                    pass

        # Close clips in reverse order
        for clip_obj in reversed([comp, bg, txt_clip, vid, clip]):
            safe_close(clip_obj)
        
        import gc
        gc.collect()

def format_youtube_title(title, hashtags, num_hashtags=3):
    # Clean the title first
    clean = clean_title(title)
    
    # Add random hashtags at the end
    tags = random.sample(hashtags, min(num_hashtags, len(hashtags)))
    
    # Combine title with hashtags
    return f"{clean} {' '.join(tags)}"

def clean_title(title):
    # Remove common dashcam model patterns
    patterns = [
        r'\[.*?]',           # Anything in square brackets
        r'\(.*?\)',          # Anything in parentheses
        r'dashcam\s*shorts', # Remove "dashcam shorts"
        r'unknown\s*dashcam', # Remove "unknown dashcam"
        r'viofo\s*[a-z0-9]+', # Remove Viofo model numbers
        r'dashcam',          # Remove standalone "dashcam"
    ]
    
    cleaned = title.lower()
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Clean up extra spaces and capitalize
    cleaned = ' '.join(cleaned.split())
    cleaned = cleaned.strip()
    cleaned = cleaned.capitalize()
    
    return cleaned

def process_channel_with_utf8_recovery(profile):
    """Wrapper around process_channel with UTF-8 error recovery via post skipping"""
    try:
        return process_channel(profile)
    except (UnicodeDecodeError, UnicodeEncodeError) as ue:
        # If we get a UTF-8 error, it means a specific post is causing issues
        # The system should automatically skip it and try the next one
        print(f"UTF-8 error encountered: {ue}")
        print("The problematic post will be automatically skipped and marked as processed.")
        
        # Try once more - the problematic post should now be in the skipped list
        try:
            return process_channel(profile)
        except (UnicodeDecodeError, UnicodeEncodeError):
            # If it still fails, give a clear error message
            subreddit = profile.get('subreddit', 'unknown')
            raise Exception(f"Persistent UTF-8 encoding issues with subreddit '{subreddit}'. Multiple posts contain incompatible characters. Consider trying a different subreddit or contact support.")

def process_channel(profile):
    """Process a single channel using the exact logic from bestcarcollisions.py"""
    
    # Extract channel data from profile
    CHANNEL = {
        "label": profile["label"],
        "subreddit": profile["subreddit"],
        "yt_token": os.path.basename(profile["yt_token"]),
        "music_dir": profile["music_dir"],
        "hashtags": profile["hashtags"],
        "sample_titles": profile["sample_titles"],
        "horizontal_zoom": profile.get("horizontal_zoom", 1.4),  # Default to 1.4x if not specified
        "font": profile.get("font", {})  # Get font config from profile
    }
    
    # Validate required channel configuration
    if not CHANNEL["subreddit"] or CHANNEL["subreddit"].strip() == "":
        raise Exception(f"Configuration Error: No subreddit specified for channel '{CHANNEL['label']}'. Please set a valid subreddit in the channel profile (e.g., 'carcrash', 'dashcam', etc.)")
    
    if not CHANNEL["yt_token"] or CHANNEL["yt_token"].strip() == "":
        raise Exception(f"Configuration Error: No YouTube token file specified for channel '{CHANNEL['label']}'. Please set a YouTube token file in the channel profile.")
    
    # Clean subreddit name (remove r/ prefix if present)
    CHANNEL["subreddit"] = CHANNEL["subreddit"].strip().lstrip("r/").strip()
    if not CHANNEL["subreddit"]:
        raise Exception(f"Configuration Error: Invalid subreddit name for channel '{CHANNEL['label']}'. Subreddit cannot be empty after cleaning.")
    
    # Check if this is test mode from profile (GUI sets this)
    gui_test_mode = profile.get("test_mode", False)
    
    # Get callbacks if provided by GUI
    progress_callback = profile.get("_gui_progress_callback", None)
    abort_callback = profile.get("_gui_abort_callback", None)
    gui_mode = profile.get("_gui_mode", False)
    
    def check_abort():
        """Check if processing should be aborted"""
        if abort_callback and abort_callback():
            raise Exception("Process aborted by user")
    
    def update_progress(stage, progress):
        """Update progress if callback is available"""
        if progress_callback:
            progress_callback(stage, progress)
        # Also check for abort when updating progress
        check_abort()
    
    def gui_print(message):
        """Print only if not in GUI mode, or if it's an important message"""
        if not gui_mode:
            print(message)

    # Set up logging path
    LOG_PATH = os.path.join(BASE_DIR, "bot.log")

    # Configure console logging for clean output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    
    # Configure file logging for detailed output
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    # Set up logging for the channel
    class ChannelFilter(logging.Filter):
        def filter(self, record):
            record.channel = CHANNEL["label"]
            return True

    # Apply channel filter to both handlers
    console_handler.addFilter(ChannelFilter())
    file_handler.addFilter(ChannelFilter())

    # Reset root logger handlers
    logging.getLogger().handlers = []
    logging.getLogger().addHandler(console_handler)
    logging.getLogger().addHandler(file_handler)

    wait_for_internet_connection()

    gui_print(f"\n📺 === YouTube Shorts Bot ===")
    gui_print(f"Channel: {CHANNEL['label']} | Subreddit: r/{CHANNEL['subreddit']}")
    
    # Only show test mode prompt if GUI hasn't set it
    if not gui_test_mode and not gui_mode:
        gui_print(f"\n🔧 Test Mode: Type '1' within 10 seconds to enable")
        gui_print("(Test mode: private upload, no daily limit, no record keeping)")
        gui_print("⏰ Waiting for input...")

    # Determine test mode - check GUI setting first, then manual input
    is_test_mode = gui_test_mode
    
    if not gui_test_mode and not gui_mode:
        # Only prompt for manual test mode if not set by GUI
        # Wait for test mode activation with proper timeout handling
        try:
            import msvcrt
            start_time = time.time()
            while time.time() - start_time < 10:
                check_abort()  # Check for abort during test mode wait
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode()
                    print(f"Type '1' for test mode (10s) [{CHANNEL['label']}]: {key}")
                    if key == '1':
                        is_test_mode = True
                        break
                time.sleep(0.1)
        except (ImportError, AttributeError):
            # Fallback for non-Windows systems
            import select
            i, _, _ = select.select([sys.stdin], [], [], 10)
            if i:
                if sys.stdin.readline().strip() == "1":
                    is_test_mode = True

    if is_test_mode:
        gui_print("\n🧪 === TEST MODE ACTIVATED ===")
        gui_print("✓ Video will be uploaded as private")
        gui_print("✓ Upload will not be recorded in history")
        gui_print("✓ Daily limit will be ignored")
        if gui_test_mode:
            gui_print("✓ Test mode set by GUI")
        gui_print("")
    else:
        gui_print("\n📅 Production mode - will check daily limits\n")

    # Reddit setup with UTF-8 error handling
    gui_print("🔗 Connecting to Reddit...")
    update_progress("fetching", 15)
    
    # Check for abort before Reddit connection
    check_abort()
    
    try:
        reddit = praw.Reddit(
            client_id=config.REDDIT_CLIENT_ID,
            client_secret=config.REDDIT_CLIENT_SECRET,
            user_agent=config.REDDIT_USER_AGENT,
            check_for_updates=False,
            ratelimit_seconds=60,
        )
        
        # Check for abort before testing connection
        check_abort()
        
        # Test the connection by making a simple request
        test_sub = reddit.subreddit(CHANNEL["subreddit"])
        test_sub.display_name  # This will trigger a request to Reddit
        gui_print(f"✅ Successfully connected to Reddit r/{CHANNEL['subreddit']}")
    except (UnicodeDecodeError, UnicodeEncodeError) as ue:
        raise Exception(f"UTF-8 encoding error during Reddit connection: {str(ue)}. This usually happens with special characters in Reddit data or network issues. Try again or check your internet connection.")
    except Exception as e:
        raise Exception(f"Failed to connect to Reddit: {str(e)}")

    # YouTube setup
    gui_print("📺 Connecting to YouTube...")
    update_progress("fetching", 20)
    
    # Check for abort before YouTube setup
    check_abort()
    
    tok = os.path.join(TOKENS_DIR, CHANNEL["yt_token"])
    
    # Validate token file path
    if not CHANNEL["yt_token"] or CHANNEL["yt_token"] in ["", ".json", "yt_token_.json"]:
        raise Exception(f"❌ YouTube Token Error: Invalid token filename '{CHANNEL['yt_token']}' for channel '{CHANNEL['label']}'. Please specify a valid token file name (e.g., 'yt_token_mychannel.json') in the channel profile.")
    
    creds = None
    
    # Check for backup files that might indicate previous corruption
    backup_file = tok + ".backup"
    if os.path.exists(backup_file) and not os.path.exists(tok):
        gui_print(f"🔧 Found backup token file but no active token for {CHANNEL['yt_token']}")
        gui_print("  Attempting to restore token from backup...")
        try:
            # Try to restore the backup file
            import shutil
            shutil.copy2(backup_file, tok)
            gui_print("✅ Token restored from backup successfully")
            
            # Test if the restored token is valid
            from google.oauth2.credentials import Credentials
            try:
                test_creds = Credentials.from_authorized_user_file(tok, SCOPES)
                if test_creds and not test_creds.expired:
                    gui_print("✅ Restored token is valid and not expired")
                else:
                    gui_print("⚠️ Restored token may be expired but will attempt refresh")
            except Exception as test_error:
                gui_print(f"⚠️ Restored token validation failed: {test_error}")
                gui_print(" 🗑️ Removing invalid backup, will regenerate fresh token")
                os.remove(tok)
                os.remove(backup_file)
                
        except Exception as e:
            gui_print(f"❌ Could not restore token from backup: {e}")
            gui_print("🗑️ Removing invalid backup file to start fresh...")
            try:
                os.remove(backup_file)
                gui_print("✅ Old backup file removed successfully")
            except Exception as cleanup_error:
                gui_print(f"⚠️ Could not remove backup file: {cleanup_error}")
    
    if os.path.exists(tok):
        from google.oauth2.credentials import Credentials
        try:
            creds = Credentials.from_authorized_user_file(tok, SCOPES)
            gui_print(f"✅ Found existing token: {CHANNEL['yt_token']}")
            gui_print(f"🔍 Token valid: {creds.valid}")
            gui_print(f"🔍 Token expired: {creds.expired}")
            if hasattr(creds, 'expiry') and creds.expiry:
                gui_print(f"🔍 Token expires: {creds.expiry}")
        except UnicodeDecodeError as e:
            gui_print(f"🔧 Token file {CHANNEL['yt_token']} is corrupted (UTF-8 error): {e}")
            gui_print("🔄 Removing corrupted token file, will regenerate...")
            try:
                # Move to backup before removing
                if os.path.exists(backup_file):
                    os.remove(backup_file)
                os.rename(tok, backup_file)
                gui_print("✅ Corrupted token file backed up and removed")
            except Exception as cleanup_error:
                gui_print(f"⚠️ Could not backup corrupted token file: {cleanup_error}")
                try:
                    os.remove(tok)
                    gui_print("✅ Corrupted token file removed")
                except:
                    pass
            creds = None
        except Exception as e:
            gui_print(f"🔧 Error loading token file {CHANNEL['yt_token']}: {e}")
            gui_print("🔄 Will regenerate token...")
            creds = None
    else:
        gui_print(f"📝 No token file found: {CHANNEL['yt_token']}")
        gui_print("🔄 First-time setup required for this channel")
    if not creds or not creds.valid:
        gui_print(f"🔧 Credential validation result:")
        gui_print(f"   - creds exists: {creds is not None}")
        if creds:
            gui_print(f"   - creds.valid: {creds.valid}")
            gui_print(f"   - creds.expired: {creds.expired}")
            gui_print(f"   - has refresh_token: {bool(creds.refresh_token)}")
        
        from google.auth.transport.requests import Request
        if creds and creds.expired and creds.refresh_token:
            gui_print("🔄 Token is expired but has refresh_token, attempting to refresh...")
            try:
                creds.refresh(Request())
                gui_print("✅ Token refreshed successfully!")
                
                # Save the refreshed token
                try:
                    with open(tok, "w", encoding='utf-8') as token:
                        token.write(creds.to_json())
                    gui_print("✅ Refreshed token saved to file")
                except Exception as save_error:
                    gui_print(f"⚠️ Could not save refreshed token: {save_error}")
                    
            except Exception as refresh_error:
                gui_print(f"❌ Token refresh failed: {refresh_error}")
                gui_print("🔄 Will require full re-authentication...")
                creds = None
        else:
            gui_print("\n🔐 YouTube Authentication Required")
            gui_print(f"📺 Setting up token for channel: {CHANNEL['label']}")
            gui_print("🌐 Browser will open - please:")
            gui_print("  1. Sign into your Google account")
            gui_print("  2. Grant permissions to YouTube Shorts Bot")
            gui_print("  3. SELECT THE CORRECT YOUTUBE CHANNEL for this profile")
            gui_print(f"  4. Choose the channel that matches: {CHANNEL['label']}")
            gui_print("⏳ Waiting for authentication...")
            
            # Check for abort before starting OAuth flow
            check_abort()
            
            flow = InstalledAppFlow.from_client_secrets_file(config.YT_CLIENT_SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)
            
            # Check for abort after authentication
            check_abort()
            
            gui_print("✅ Authentication completed successfully!")
            gui_print(f"🔗 Token will be saved as: {CHANNEL['yt_token']}")
        
        # Save token with verification
        try:
            with open(tok, "w", encoding='utf-8') as token:
                token.write(creds.to_json())
            gui_print(f"✅ Token saved successfully to {CHANNEL['yt_token']}")
            
            # Verify the token file was saved correctly
            if os.path.exists(tok) and os.path.getsize(tok) > 0:
                gui_print("✅ Token file verified - authentication complete!")
                gui_print("🎉 You won't need to re-authenticate unless the token expires.")
            else:
                gui_print("⚠️ Token file verification failed - file is empty or missing")
                gui_print("🔄 You may need to authenticate again next time")
                
        except Exception as e:
            gui_print(f"❌ Error: Could not save token file {CHANNEL['yt_token']}: {e}")
            gui_print("🔄 Authentication completed but token not saved - will need to re-auth next time")
            # Don't fail the process, but log the issue
    
    # Verify credentials are valid before proceeding
    if not creds or not creds.valid:
        error_msg = f"❌ YouTube Authentication Error: Failed to obtain valid YouTube credentials for channel '{CHANNEL['label']}'"
        
        if not creds:
            error_msg += "\n   💡 Solution: The authentication process failed or was cancelled."
            error_msg += f"\n   📋 Check that token file '{CHANNEL['yt_token']}' is properly configured in the channel profile."
            error_msg += "\n   🔄 Try running the channel again to re-authenticate."
        elif creds and not creds.valid:
            error_msg += "\n   💡 Solution: The token exists but is invalid or corrupted."
            error_msg += f"\n   📋 Token file: {tok}"
            error_msg += "\n   🔄 The token will be regenerated on next run."
        
        error_msg += "\n   📖 Make sure you have a valid YouTube channel and proper OAuth setup."
        raise Exception(error_msg)
        
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    gui_print(f"🎬 YouTube API connection established for {CHANNEL['label']}")

    # Daily upload check
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    daily_limit = profile.get("daily_upload_limit", 1)
    print(f"📅 Checking uploads for date: {today}")
    gui_print(f"📊 Daily Upload Limit: {daily_limit} video(s)")
    
    uploads_file = os.path.join(PROCESSED_DIR, f"processed_{CHANNEL['label']}.json")
    try:
        with open(uploads_file, "r", encoding='utf-8') as f:
            uploads = json.load(f)
    except FileNotFoundError:
        uploads = []
    
    if not is_test_mode:
        # Count uploads for today
        uploads_today = [u for u in uploads if u.get("date") == today]
        uploads_count = len(uploads_today)
        
        if uploads_count >= daily_limit:
            gui_print(f"⏹️ Daily upload limit reached ({uploads_count}/{daily_limit} for {today}). Skipping...")
            gui_print(f"💡 To upload more videos today, increase the daily_upload_limit in your profile settings or use test mode.")
            
            # For GUI mode, send a specific message that can be detected
            if gui_mode and progress_callback:
                progress_callback("daily_limit_reached", 100)
            
            return
        else:
            gui_print(f"📈 Upload status: {uploads_count}/{daily_limit} uploads completed for {today}")
    else:
        gui_print("🧪 Test mode: Skipping daily upload check")

    # Fetch candidates using original script logic with UTF-8 error handling
    gui_print(f"🔍 Fetching video candidates from r/{CHANNEL['subreddit']}...")
    update_progress("fetching", 25)
    done_ids = {u["id"] for u in uploads if "id" in u}
    
    check_abort()  # Check for abort before fetching candidates
    
    try:
        # Determine fetch parameters based on recovery mode
        fetch_limit = profile.get('_fetch_limit', 40)
        safe_mode = profile.get('_safe_mode', False)
        
        # Get video selection settings
        video_selection = profile.get('video_selection', {})
        sort_method = video_selection.get('sort_method', 'top_month')
        fallback_enabled = video_selection.get('enable_fallback', True)
        
        # Build fallback chain based on settings
        fallback_chain = []
        if sort_method == 'top_month':
            fallback_chain = ['top_month', 'top_year', 'top_all'] if fallback_enabled else ['top_month']
        elif sort_method == 'top_year':
            fallback_chain = ['top_year', 'top_all'] if fallback_enabled else ['top_year']
        elif sort_method == 'top_all':
            fallback_chain = ['top_all']
        elif sort_method == 'hot':
            fallback_chain = ['hot', 'top_month', 'top_year', 'top_all'] if fallback_enabled else ['hot']
        elif sort_method == 'new':
            fallback_chain = ['new', 'hot', 'top_month', 'top_year', 'top_all'] if fallback_enabled else ['new']
        else:
            # Default fallback for unknown sort methods
            fallback_chain = ['top_month', 'top_year', 'top_all']
        
        if safe_mode:
            print("🛡️ Running in safe mode to avoid encoding issues...")
        
        print(f"Using video selection: {sort_method} with fallback: {fallback_enabled}")
        
        candidates = fetch_candidates(reddit, CHANNEL["subreddit"], done_ids, fetch_limit, safe_mode, sort_method, fallback_chain)
    except (UnicodeDecodeError, UnicodeEncodeError) as ue:
        raise Exception(f"UTF-8 encoding error while fetching Reddit posts: {str(ue)}. This usually happens with special characters in Reddit post titles or content. Try processing a different subreddit or try again later.")
    except Exception as e:
        raise Exception(f"Error fetching Reddit posts: {str(e)}")

    if not candidates:
        # Log error if no suitable videos found in any category
        error_msg = f"No suitable videos found for r/{CHANNEL['subreddit']} using {sort_method}"
        if fallback_enabled:
            error_msg += f" or any fallback methods ({', '.join(fallback_chain)})"
        error_msg += ". Try adjusting video selection settings or check if the subreddit has recent video posts."
        raise Exception(error_msg)
        # Always show errors
        print("❌ No suitable videos found")
        print(f"ℹ️ Already processed {len(done_ids)} videos")
        return

    check_abort()  # Check for abort before processing video
    post = candidates[0]
    duration = _reddit_duration(post)
    
    # Safely extract post data with UTF-8 handling
    try:
        post = candidates[0]
        duration = _reddit_duration(post)
        
        # Handle both PRAW and SafePost objects
        if hasattr(post, 'title') and hasattr(post, 'url') and hasattr(post, 'id'):
            # SafePost object - already sanitized
            safe_title = safe_get_post_attribute(post, 'title', 'Post with encoding issues')
            safe_url = safe_get_post_attribute(post, 'url', '')
            post_id = safe_get_post_attribute(post, 'id', 'unknown')
        else:
            # PRAW object - use safe attribute access
            safe_title = safe_get_post_attribute(post, 'title', 'Video Title')
            safe_url = safe_get_post_attribute(post, 'url', '')
            post_id = safe_get_post_attribute(post, 'id', 'unknown')
        
        if not safe_url:
            raise Exception("Could not extract valid URL from post")
            
    except (UnicodeDecodeError, UnicodeEncodeError) as e:
        # If we can't process this post, skip it and try the next one
        try:
            post_id = safe_get_post_attribute(candidates[0], 'id', 'unknown') if candidates else 'unknown'
        except:
            post_id = 'unknown'
            
        print(f"❌ UTF-8 error processing selected post {post_id}: {e}")
        print("UTF-8 error encountered: 'utf-8' codec can't decode byte 0x80 in position 0: invalid start byte")
        print("The problematic post will be automatically skipped and marked as processed.")
        add_to_processed_list(post_id, f"Processing UTF-8 error: {str(e)}", CHANNEL["subreddit"])
        
        # Try the next candidate
        if len(candidates) > 1:
            print("🔄 Trying next candidate...")
            try:
                post = candidates[1]
                duration = _reddit_duration(post)
                
                # Handle both PRAW and SafePost objects for backup
                if hasattr(post, 'title') and hasattr(post, 'url') and hasattr(post, 'id'):
                    safe_title = safe_get_post_attribute(post, 'title', 'Post with encoding issues')
                    safe_url = safe_get_post_attribute(post, 'url', '')
                    post_id = safe_get_post_attribute(post, 'id', 'unknown')
                else:
                    safe_title = safe_get_post_attribute(post, 'title', 'Video Title')
                    safe_url = safe_get_post_attribute(post, 'url', '')
                    post_id = safe_get_post_attribute(post, 'id', 'unknown')
                
                if not safe_url:
                    raise Exception("Could not extract valid URL from backup post")
                    
                print(f"✅ Successfully using backup candidate: {safe_title}")
            except (UnicodeDecodeError, UnicodeEncodeError) as e2:
                try:
                    post_id = sanitize_text_for_utf8(str(getattr(candidates[1], 'id', 'unknown')))
                except:
                    post_id = 'unknown'
                print(f"❌ UTF-8 error in backup post {post_id}: {e2}")
                print("UTF-8 error encountered: 'utf-8' codec can't decode byte 0x80 in position 0: invalid start byte")
                print("The problematic post will be automatically skipped and marked as processed.")
                add_to_processed_list(post_id, f"Processing UTF-8 error: {str(e2)}", CHANNEL["subreddit"])
                raise Exception(f"Multiple UTF-8 errors in candidate posts. The problematic posts have been skipped. Please try processing again.")
        else:
            raise Exception(f"UTF-8 error in the only available post. The post has been skipped. Please try processing again to get a new post.")
    except Exception as e:
        print(f"❌ Error processing post data: {e}")
        print("This usually happens with special characters in Reddit posts.")
        return
    
    # Show key info in GUI mode but less verbose
    try:
        post_score = getattr(post, 'score', 0) if hasattr(post, 'score') else safe_get_post_attribute(post, 'score', 0)
        post_score = int(post_score) if post_score else 0
    except:
        post_score = 0
        
    if gui_mode:
        print(f"✅ Selected: {safe_title} ({duration}s, {post_score} upvotes)")
    else:
        print(f"✅ Selected video:")
        print(f"   📝 Title: {safe_title}")
        print(f"   ⏱️ Duration: {duration} seconds")
        print(f"   👍 Score: {post_score} upvotes")

    # Video processing using original script method
    gui_print("\n📥 Downloading video...")
    update_progress("processing", 40)
    
    try:
        # Use original download method with safe URL
        tmp_path = os.path.join(OUT_DIR, f"{uuid.uuid4()}.%(ext)s")
        video_path = dl_video(safe_url, tmp_path, abort_callback)
        
        check_abort()  # Check for abort before video conversion
        
        # Generate output path
        out_path = os.path.join(OUT_DIR, f"{uuid.uuid4()}.mp4")
        
        # Generate subtitle from sample titles with UTF-8 safe handling
        try:
            subtitle = random.choice(CHANNEL["sample_titles"]) if CHANNEL["sample_titles"] else None
            if subtitle:
                subtitle = sanitize_text_for_utf8(subtitle)
        except Exception:
            subtitle = None  # No fallback text if sample titles fail
        
        if subtitle:
            print(f"Using subtitle: '{subtitle}'")
        else:
            print("No subtitle - no sample titles configured for this channel")
        
        # Convert to vertical YouTube Short with text overlay and music
        update_progress("rendering", 60)
        music_volume = profile.get('music_volume', 0.3)  # Get music volume from profile, default 30%
        music_used = make_vertical_short(video_path, subtitle, out_path, CHANNEL["music_dir"], CHANNEL["horizontal_zoom"], CHANNEL["font"], music_volume, abort_callback)
        
        check_abort()  # Check for abort after video rendering
        
        # Apply intelligent audio detection and music addition if needed
        if process_video_with_audio_check:
            music_mode = profile.get('music_mode', 'smart')
            
            if music_mode != 'disabled':
                print("🔊 Analyzing audio content...")
                
                # Create a logging function for the audio module
                def audio_log(message):
                    print(message)
                    if progress_callback:
                        try:
                            progress_callback("audio_processing", 65, message)
                        except:
                            pass
                
                # Process the video with audio detection
                final_video_path = process_video_with_audio_check(out_path, profile, log_callback=audio_log)
                
                # Debug logging for path tracking
                print(f"🔍 Debug: Original out_path: {out_path}")
                print(f"🔍 Debug: Final video path from audio processing: {final_video_path}")
                
                # If a new file was created with music, update the path
                if final_video_path != out_path:
                    print(f"🔍 Debug: New file created with music, updating path")
                    
                    # Clean up the original file if it still exists
                    if os.path.exists(out_path):
                        try:
                            os.remove(out_path)
                            print(f"🔍 Debug: Removed original file: {out_path}")
                        except:
                            pass
                    else:
                        print(f"🔍 Debug: Original file already removed by audio processing")
                    
                    # Always update the output path when a new file is created
                    out_path = final_video_path
                    print(f"✅ Video enhanced with background music: {os.path.basename(out_path)}")
                    print(f"🔍 Debug: Updated out_path to: {out_path}")
                else:
                    print(f"🔍 Debug: No path change needed (paths are identical)")
            else:
                print("🎵 Music processing disabled for this channel")
        
        # Clean up temp file
        if os.path.exists(video_path):
            try:
                os.remove(video_path)
            except PermissionError:
                print(f"Warning: Could not remove temp file {video_path}")
        
        print("✅ YouTube Short ready!")
        if music_used:
            print(f"🎵 Background music: {music_used}")

    except Exception as e:
        print(f"❌ Error processing video: {e}")
        return

    # YouTube upload
    check_abort()  # Check for abort before upload
    gui_print("🚀 Uploading YouTube Short...")
    update_progress("uploading", 80)
    
    try:
        # Generate title with hashtags (censor bad words) with UTF-8 safe handling
        try:
            video_title = format_youtube_title(safe_title, CHANNEL["hashtags"])
            censored_title = censor(video_title)
        except Exception:
            # Fallback title generation
            censored_title = "Amazing Short Video " + " ".join(CHANNEL["hashtags"][:3])
            censored_title = sanitize_text_for_utf8(censored_title)
        
        # Set privacy status
        privacy_status = "private" if is_test_mode else "public"
        
        body = {
            'snippet': {
                'title': censored_title[:100],  # YouTube title limit
                'tags': [tag.replace('#', '') for tag in CHANNEL["hashtags"][:10]],  # Remove # for tags
                'categoryId': '24'  # Entertainment category
            },
            'status': {
                'privacyStatus': privacy_status,
                'madeForKids': False,
                'selfDeclaredMadeForKids': False
            }
        }
        
        # Upload the video
        check_abort()  # Check for abort right before uploading
        # Debug logging for upload path
        print(f"🔍 Debug: About to upload file: {out_path}")
        print(f"🔍 Debug: File exists: {os.path.exists(out_path)}")
        if os.path.exists(out_path):
            print(f"🔍 Debug: File size: {os.path.getsize(out_path)} bytes")
        
        # Use smaller chunk size for more responsive abort checking
        media = MediaFileUpload(out_path, chunksize=1024*1024, resumable=True)  # 1MB chunks instead of full file
        request = yt.videos().insert(
            part='snippet,status',
            body=body,
            media_body=media
        )
        
        response = None
        while response is None:
            check_abort()  # Check for abort during upload
            status, response = request.next_chunk()
            if status and not gui_mode:
                print(f"Upload progress: {int(status.progress() * 100)}%")
        
        video_id_yt = response['id']
        
        # Always show success message
        print("✅ YouTube Short uploaded successfully!")
        if gui_mode:
            print(f"🔗 https://youtube.com/shorts/{video_id_yt}")
        else:
            print(f"📺 Video ID: {video_id_yt}")
            print(f"🔗 URL: https://youtube.com/shorts/{video_id_yt}")
        
    except Exception as e:
        # Always show errors
        print(f"❌ Upload failed: {e}")
        video_id_yt = None
        # Re-raise exception for GUI to handle if in GUI mode
        if gui_mode:
            raise e

    # Save upload record
    if video_id_yt:  # Only save if upload was successful
        if not is_test_mode:
            # Check for abort before saving record - if aborted here, video was uploaded but won't count against limit
            check_abort()
            
            upload_record = {
                "id": post_id,  # Use the safe post_id we extracted earlier
                "title": safe_title,  # Use the sanitized title
                "date": today,
                "youtube_id": video_id_yt,
                "url": safe_url  # Use the sanitized URL
            }
            uploads.append(upload_record)
            with open(uploads_file, "w", encoding='utf-8') as f:
                json.dump(uploads, f, indent=2, ensure_ascii=False)
            print(f"💾 Upload record saved")
        else:
            print("🧪 Test mode: Skipping upload record")
    else:
        # Always show record-keeping messages
        print("❌ Upload failed - not saving record")

    gui_print("🧹 Cleaning up...")
    update_progress("cleanup", 95)
    
    # Force garbage collection to release file handles
    import gc
    gc.collect()
    time.sleep(1)  # Reduced sleep time

    # Cleanup with improved retry logic for Windows file locking
    cleanup_success = False
    max_retries = 3  # Reduced retries
    
    if os.path.exists(out_path):
        for attempt in range(max_retries):
            check_abort()  # Check for abort during cleanup attempts
            try:
                # Try multiple cleanup strategies
                
                # Strategy 1: Direct delete
                os.remove(out_path)
                if not gui_mode:
                    print("✅ Cleanup complete")
                cleanup_success = True
                break
                
            except PermissionError:
                if attempt < max_retries - 1:
                    if not gui_mode:
                        print(f"🔄 Retrying cleanup... (attempt {attempt + 1}/{max_retries})")
                    gc.collect()
                    time.sleep(2)
                else:
                    # Strategy 2: Try to move to temp directory for later deletion
                    try:
                        import tempfile
                        temp_dir = tempfile.gettempdir()
                        temp_name = os.path.join(temp_dir, f"yt_bot_cleanup_{uuid.uuid4()}.mp4")
                        os.rename(out_path, temp_name)
                        if not gui_mode:
                            print("✅ File moved to temp directory for system cleanup")
                        cleanup_success = True
                        break
                    except:
                        if not gui_mode:
                            print("⚠️ File cleanup will be handled by system later")
                        
            except Exception as e:
                if not gui_mode:
                    print(f"⚠️ Cleanup note: {e}")
                break
    else:
        cleanup_success = True  # File doesn't exist, so "cleanup" succeeded
    
    if not cleanup_success and not gui_mode:
        print("📝 Output file kept - can be manually removed later if needed")

def main():
    # Check for command line arguments to process specific channel
    target_channel = None
    if len(sys.argv) > 1:
        target_channel = sys.argv[1]
        print(f"🎯 Targeting specific channel: {target_channel}")
    
    profiles = load_profiles()
    
    if target_channel:
        # Process only the specified channel
        if target_channel in profiles:
            print(f"📋 Processing single channel: {target_channel}")
            print("=" * 50)
            try:
                print(f"\n🎬 Processing Channel: {target_channel}")
                print("-" * 30)
                process_channel_with_utf8_recovery(profiles[target_channel])
                print("✅ Channel complete")
            except Exception as e:
                print(f"\n❌ ERROR processing {target_channel}: {str(e)}")
                traceback.print_exc()
        else:
            print(f"❌ Channel '{target_channel}' not found in profiles!")
            print(f"Available channels: {', '.join(profiles.keys())}")
            return
    else:
        # Process all channels
        print(f"📋 Loaded {len(profiles)} channel profiles")
        print("=" * 50)
        
        for i, (label, profile) in enumerate(profiles.items(), 1):
            try:
                print(f"\n🎬 Processing Channel {i}/{len(profiles)}: {label}")
                print("-" * 30)
                process_channel_with_utf8_recovery(profile)
                print("✅ Channel complete")
            except Exception as e:
                print(f"\n❌ ERROR processing {label}: {str(e)}")
                traceback.print_exc()
        
        print(f"\n🎉 All channels processed!")
    print("=" * 50)

if __name__ == "__main__":
    main()
