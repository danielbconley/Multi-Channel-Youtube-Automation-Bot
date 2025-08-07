#!/usr/bin/env python3
"""
YouTube Shorts Bot - GUI Manager
────────────────────────────────────────────────────────
• Graphical interface for managing channel profiles
• Individual and bulk channel processing
• Real-time status monitoring and logs
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
import json
import os
import sys
import threading
import subprocess
import queue
import shutil
import pickle
import webbrowser
from datetime import datetime
import re
import importlib
from datetime import datetime

# Add the current directory to Python path to import process_videos
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Defer heavy imports until they're needed
process_videos = None

def load_process_videos():
    """Lazy load process_videos module only when needed"""
    global process_videos
    if process_videos is None:
        try:
            import process_videos as pv
            process_videos = pv
        except ImportError as e:
            # Initialize tkinter to show error dialog
            root = tk.Tk()
            root.withdraw()  # Hide the main window
            
            error_msg = f"Missing dependencies detected!\n\nError: {str(e)}\n\nRequired packages:\n• moviepy\n• Pillow (PIL)\n• google-auth\n• google-auth-httplib2\n• google-api-python-client\n• requests\n• pytz\n• yt-dlp\n• praw\n• numpy\n• opencv-python\n\nPlease install these packages and restart the application."
            messagebox.showerror("Missing Dependencies", error_msg)
            root.destroy()
            sys.exit(1)
    return process_videos

class YouTubeBotsGUI:
    def __init__(self):
        # Create the main window immediately
        self.root = tk.Tk()
        self.root.title("🎬 YouTube Shorts Bot Manager")
        self.root.geometry("1400x900")
        self.root.resizable(False, False)  # Lock window size - no resizing allowed
        self.root.configure(bg='#f8f9fa')  # Light theme background
        
        # Handle window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Remove the default tkinter feather icon completely
        try:
            # Method 1: Create a transparent 1x1 pixel icon
            self.window_icon = tk.PhotoImage(width=1, height=1)  # Store reference to prevent garbage collection
            self.window_icon.blank()  # Make it transparent
            self.root.iconphoto(True, self.window_icon)
        except:
            try:
                # Method 2: Use empty string to remove icon
                self.root.iconbitmap('')
            except:
                try:
                    # Method 3: Set window attributes
                    self.root.wm_iconbitmap('')
                except:
                    # Method 4: Use default system icon instead
                    try:
                        self.root.iconbitmap(default='')
                    except:
                        pass  # Give up and keep default
        
        # Configure modern style
        self.setup_styles()
        
        # Variables - Initialize immediately after root window
        self.profiles = {}
        self.selected_profile = None
        self.processing_queue = queue.Queue()
        self.is_processing = False
        self.abort_processing = False  # Flag to abort any running process
        self._warning_shown = False  # Flag to prevent duplicate warnings
        self._reddit_warning_shown = False  # Flag for Reddit warning
        self._storage_warning_shown = False  # Flag for storage warning
        
        # Dialog open flag to prevent event conflicts
        self._dialog_open = False
        
        # File existence cache for better performance
        self._file_cache = {}
        self._cache_expiry = {}
        
        # Widget style cache for better performance
        self._style_cache = {}
        
        # Configure common styles once for better performance
        self.style = ttk.Style()
        self._configure_common_styles()
        
        # Unsaved changes tracking
        self.has_unsaved_changes = False
        self.has_unsaved_startup_changes = False  # Track startup management changes
        self.original_profile_data = {}  # Store original data for comparison
        self.original_startup_states = {}  # Store original startup states for comparison
        self.loading_profile = False  # Flag to prevent tracking during loading
        
        # Load profiles immediately
        self.load_profiles()
        
        # Setup GUI immediately
        self.setup_gui()
        
        # Add global error handling for widgets
        self.add_global_error_protection()
        
        # Start monitoring thread
        self.root.after(100, self.process_queue)
        
        # Simple period animation for processing stages
        self.active_animations = {}  # Track lines that need period animation
        self.animation_timer = None
        self.dot_count = 1  # Start with 1 dot
        
        # Center and show the window
        self.center_window()
        
        # Check warnings after GUI is completely ready
        self.root.after(500, self.check_startup_warnings)  # Increased delay to 500ms

    def check_startup_warnings(self):
        """Check all warnings after GUI is completely initialized"""
        try:
            print("DEBUG: Starting startup warnings check...")
            
            # Check client secrets
            print("DEBUG: Checking client secrets...")
            self.check_client_secrets()
            
            # Check Reddit configuration  
            print("DEBUG: Checking Reddit config...")
            self.check_reddit_config()
            
            # Check storage space
            print("DEBUG: Checking storage space...")
            self.check_storage_space()
            
            print("DEBUG: Finished startup warnings check")
            
        except Exception as e:
            print(f"Error checking startup warnings: {e}")

    def ensure_profiles_file(self):
        """Create an empty profiles.json file if it doesn't exist"""
        try:
            if not os.path.exists('profiles.json'):
                # Create empty profiles file with basic structure
                empty_profiles = {}
                with open('profiles.json', 'w', encoding='utf-8') as f:
                    json.dump(empty_profiles, f, indent=2)
                if hasattr(self, 'log_text'):
                    self.log_message("📁 Created empty profiles.json file")
        except Exception as e:
            if hasattr(self, 'log_text'):
                self.log_message(f"❌ Error creating profiles.json: {str(e)}")

    def center_window(self):
        """Center the window on screen"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"+{x}+{y}")

    def start_period_animation(self, stage_name):
        """Start animating periods for a processing stage"""
        if hasattr(self, 'log_text') and stage_name not in self.active_animations:
            # Stop all other animations first to ensure only current stage animates
            self.stop_all_animations()
            
            # Find the last line with this stage in the text widget
            content = self.log_text.get(1.0, tk.END)
            lines = content.strip().split('\n')
            
            # Look for the stage line (like "🔍 Fetching...")
            for i in range(len(lines) - 1, -1, -1):
                line = lines[i]
                if stage_name.lower() in line.lower() and "..." in line:
                    # Found the line, store its info
                    base_line = line.replace("...", "").rstrip('.')
                    self.active_animations[stage_name] = {
                        'line_index': i,  # 0-based index in the lines array
                        'base_text': base_line
                    }
                    
                    # Start the animation timer if it's not already running
                    if not self.animation_timer:
                        self.update_period_animations()
                    break
    
    def stop_all_animations(self):
        """Stop all animations and set their final state to three dots"""
        if not hasattr(self, 'log_text'):
            return
            
        # Set final state for all currently animated lines
        for stage_name, anim_data in list(self.active_animations.items()):
            try:
                line_number = anim_data['line_index'] + 1  # Tkinter uses 1-based line numbers
                base_text = anim_data['base_text']
                final_text = f"{base_text}..."  # Always end with three dots
                
                # Set the final state
                line_start = f"{line_number}.0"
                line_end = f"{line_number}.end"
                current_line = self.log_text.get(line_start, line_end)
                
                if current_line != final_text:
                    self.log_text.delete(line_start, line_end)
                    self.log_text.insert(line_start, final_text)
                    
            except tk.TclError:
                # Line doesn't exist anymore, that's fine
                pass
        
        # Clear all animations
        self.active_animations.clear()
        
        # Cancel timer
        if self.animation_timer:
            self.root.after_cancel(self.animation_timer)
            self.animation_timer = None
    
    def stop_period_animation(self, stage_name):
        """Stop animating periods for a processing stage and set final state"""
        if stage_name in self.active_animations:
            try:
                # Before removing from animations, set the final state to three dots
                anim_data = self.active_animations[stage_name]
                line_number = anim_data['line_index'] + 1  # Tkinter uses 1-based line numbers
                base_text = anim_data['base_text']
                final_text = f"{base_text}..."  # Always end with three dots
                
                # Set the final state
                line_start = f"{line_number}.0"
                line_end = f"{line_number}.end"
                current_line = self.log_text.get(line_start, line_end)
                
                if current_line != final_text:
                    self.log_text.delete(line_start, line_end)
                    self.log_text.insert(line_start, final_text)
                    
            except tk.TclError:
                # Line doesn't exist anymore, that's fine
                pass
            
            # Remove from active animations
            del self.active_animations[stage_name]
            
            # Cancel timer if no more animations
            if not self.active_animations and self.animation_timer:
                self.root.after_cancel(self.animation_timer)
                self.animation_timer = None
    
    def update_period_animations(self):
        """Update all active period animations"""
        if not self.active_animations or not hasattr(self, 'log_text'):
            return
        
        # Cycle through 1, 2, 3 dots
        self.dot_count = (self.dot_count % 3) + 1
        dots = '.' * self.dot_count
        
        # Get current content to verify line positions
        content = self.log_text.get(1.0, tk.END)
        lines = content.strip().split('\n')
        
        # Update each animated line, but verify the line still matches
        animations_to_remove = []
        for stage_name, anim_data in self.active_animations.items():
            try:
                line_index = anim_data['line_index']
                base_text = anim_data['base_text']
                
                # Verify the line still exists and contains our stage
                if line_index < len(lines):
                    current_line_content = lines[line_index]
                    # Check if this line still belongs to our stage
                    if stage_name.lower() in current_line_content.lower():
                        # Update the line in the text widget
                        line_number = line_index + 1  # Tkinter uses 1-based line numbers
                        new_text = f"{base_text}{dots}"
                        
                        line_start = f"{line_number}.0"
                        line_end = f"{line_number}.end"
                        current_widget_line = self.log_text.get(line_start, line_end)
                        
                        # Only update if the content actually changed
                        if current_widget_line != new_text:
                            self.log_text.delete(line_start, line_end)
                            self.log_text.insert(line_start, new_text)
                    else:
                        # Line no longer matches our stage, remove animation
                        animations_to_remove.append(stage_name)
                else:
                    # Line doesn't exist anymore, remove animation
                    animations_to_remove.append(stage_name)
                    
            except tk.TclError:
                # Error accessing the line, remove animation
                animations_to_remove.append(stage_name)
        
        # Remove invalid animations
        for stage_name in animations_to_remove:
            if stage_name in self.active_animations:
                del self.active_animations[stage_name]
        
        # Schedule next update if we still have animations
        if self.active_animations:
            self.animation_timer = self.root.after(600, self.update_period_animations)
        else:
            self.animation_timer = None
    
    def center_window(self):
        """Center the main window on the screen"""
        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Use the fixed window dimensions (1400x900)
        window_width = 1400
        window_height = 900
        
        # Calculate center position, but move it higher up by 40 pixels
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2 - 40
        
        # Set the window position with the correct size
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    def setup_styles(self):
        """Configure clean light theme styles"""
        style = ttk.Style()
        style.theme_use('default')  # Use default theme to avoid feather icon
        
        # Configure colors for light theme
        bg_color = '#f8f9fa'
        fg_color = '#212529'
        select_color = '#0078d4'
        button_color = '#e9ecef'
        
        # Configure styles for light mode
        style.configure('TFrame', background=bg_color)
        style.configure('TLabel', background=bg_color, foreground=fg_color)
        
        # Gray buttons - normal gray, lighter gray on hover
        style.configure('TButton', background=button_color, foreground=fg_color, borderwidth=1, relief='solid')
        style.map('TButton', background=[('active', '#dee2e6')])
        
        # Blue buttons - blue background, darker blue on hover
        style.configure('Accent.TButton', background=select_color, foreground='white', borderwidth=1, relief='solid')
        style.map('Accent.TButton', background=[('active', '#106ebe')])
        
        # Red buttons - normal gray background, red on hover
        style.configure('Danger.TButton', background=button_color, foreground=fg_color, borderwidth=1, relief='solid')
        style.map('Danger.TButton', 
                 background=[('active', '#dc3545')],
                 foreground=[('active', 'white')])
        
        # Critical buttons - always red, darker red on hover
        style.configure('Critical.TButton', background='#dc3545', foreground='white', borderwidth=1, relief='solid')
        style.map('Critical.TButton', background=[('active', '#c82333')])
        style.configure('TEntry', foreground=fg_color, fieldbackground='white', borderwidth=1, relief='solid')
        style.configure('TSpinbox', foreground=fg_color, fieldbackground='white', borderwidth=1, relief='solid')
        style.configure('TCheckbutton', background=bg_color, foreground=fg_color, focuscolor='none')
        style.map('TCheckbutton', 
                 background=[('active', bg_color)], 
                 foreground=[('active', fg_color)],
                 indicatorcolor=[('selected', select_color), ('!selected', 'white')],
                 indicatorrelief=[('selected', 'solid'), ('!selected', 'solid')])
        
        style.configure('Startup.TCheckbutton', background=bg_color, foreground=fg_color, focuscolor='none')
        style.map('Startup.TCheckbutton', 
                 background=[('active', bg_color)], 
                 foreground=[('active', fg_color)],
                 indicatorcolor=[('selected', select_color), ('!selected', 'white')],
                 indicatorrelief=[('selected', 'solid'), ('!selected', 'solid')])
        
        # Configure radio buttons with square styling (like checkboxes)
        style.configure('TRadiobutton', background=bg_color, foreground=fg_color, focuscolor='none')
        style.map('TRadiobutton', 
                 background=[('active', bg_color)], 
                 foreground=[('active', fg_color)],
                 indicatorcolor=[('selected', select_color), ('!selected', 'white')],
                 indicatorrelief=[('selected', 'solid'), ('!selected', 'solid')])
        
        # Try to make radio button indicators more square-like (platform dependent)
        try:
            # This attempts to use a more square indicator style
            style.configure('TRadiobutton', indicatorsize=12, indicatormargins=(2, 2, 4, 2))
        except Exception:
            # Fallback if advanced styling not supported
            pass
        
        style.configure('TNotebook', background=bg_color, tabmargins=[2, 5, 2, 0])
        style.configure('TNotebook.Tab', background=button_color, foreground=fg_color, padding=[12, 8], borderwidth=1)
        style.map('TNotebook.Tab', background=[('selected', 'white')])
        style.configure('Treeview', background='white', foreground=fg_color, fieldbackground='white', borderwidth=1, relief='solid')
        style.configure('TLabelframe', background=bg_color, foreground=fg_color, borderwidth=1, relief='solid')
        style.configure('TLabelframe.Label', background=bg_color, foreground=fg_color)
    
    def validate_int(self, value):
        """Validate integer input for spinboxes"""
        if value == "":
            return True  # Allow empty string
        try:
            int_val = int(value)
            # Additional range checking to prevent issues
            if -999999 <= int_val <= 999999:  # Reasonable range
                return True
            else:
                return False
        except ValueError:
            return False
        except Exception as e:
            # Log unexpected errors but don't crash
            print(f"Validation error: {e}")
            return False
    
    def validate_float(self, value):
        """Validate float input for spinboxes"""
        if value == "":
            return True  # Allow empty string
        try:
            float_val = float(value)
            # Additional range checking to prevent issues
            if -999999.0 <= float_val <= 999999.0:  # Reasonable range
                return True
            else:
                return False
        except ValueError:
            return False
        except Exception as e:
            # Log unexpected errors but don't crash
            print(f"Validation error: {e}")
            return False
    
    def validate_spinbox_value(self, spinbox_widget, tk_var, min_val, max_val):
        """Validate and correct spinbox values to prevent crashes"""
        try:
            current_value = tk_var.get()
            
            # Handle different variable types
            if isinstance(tk_var, tk.IntVar):
                if current_value < min_val or current_value > max_val:
                    # Reset to closest valid value
                    corrected_value = max(min_val, min(max_val, current_value))
                    tk_var.set(corrected_value)
                    self.log_message(f"🔧 Corrected invalid value to {corrected_value}")
            elif isinstance(tk_var, tk.DoubleVar):
                if current_value < min_val or current_value > max_val:
                    # Reset to closest valid value
                    corrected_value = max(min_val, min(max_val, current_value))
                    tk_var.set(corrected_value)
                    self.log_message(f"🔧 Corrected invalid value to {corrected_value}")
                    
        except Exception as e:
            # If there's any error, reset to a safe default
            try:
                if isinstance(tk_var, tk.IntVar):
                    safe_default = int((min_val + max_val) / 2)
                elif isinstance(tk_var, tk.DoubleVar):
                    safe_default = float((min_val + max_val) / 2)
                else:
                    safe_default = min_val
                    
                tk_var.set(safe_default)
                self.log_message(f"🔧 Reset invalid spinbox value to safe default: {safe_default}")
            except Exception as reset_error:
                self.log_message(f"⚠️ Could not reset spinbox value: {reset_error}")
    
    def safe_spinbox_click(self, event, spinbox_widget, tk_var, min_val, max_val):
        """Safely handle spinbox click events to prevent crashes"""
        try:
            # Allow the normal click behavior but catch any errors
            return None  # Let the event proceed normally
        except Exception as e:
            self.log_message(f"🛡️ Prevented spinbox click error: {e}")
            # Force a safe value if there's an error
            try:
                if isinstance(tk_var, tk.IntVar):
                    safe_val = max(min_val, min(max_val, tk_var.get()))
                    tk_var.set(safe_val)
                elif isinstance(tk_var, tk.DoubleVar):
                    safe_val = max(min_val, min(max_val, tk_var.get()))
                    tk_var.set(safe_val)
            except:
                # If even that fails, set to middle value
                middle_val = (min_val + max_val) / 2
                tk_var.set(middle_val)
            return "break"  # Stop the event from propagating
    
    def safe_spinbox_key(self, event, spinbox_widget, tk_var, min_val, max_val):
        """Safely handle spinbox key events to prevent crashes"""
        try:
            # For up/down arrow keys, handle them safely
            if event.keysym in ['Up', 'Down']:
                current_val = tk_var.get()
                if event.keysym == 'Up':
                    if isinstance(tk_var, tk.IntVar):
                        new_val = min(max_val, current_val + 1)
                    else:  # DoubleVar
                        new_val = min(max_val, current_val + 0.1)
                else:  # Down
                    if isinstance(tk_var, tk.IntVar):
                        new_val = max(min_val, current_val - 1)
                    else:  # DoubleVar
                        new_val = max(min_val, current_val - 0.1)
                
                tk_var.set(new_val)
                self.track_profile_changes()  # Mark as changed
                return "break"  # Prevent default handling
            
            return None  # Allow other keys to proceed normally
        except Exception as e:
            self.log_message(f"🛡️ Prevented spinbox key error: {e}")
            return "break"  # Stop the event from propagating
    
    def add_global_error_protection(self):
        """Add global error protection to prevent widget crashes"""
        try:
            # Add a global exception handler for Tkinter
            def handle_exception(exception, value, traceback):
                # Log the error but don't crash the GUI
                error_msg = f"GUI Error: {exception.__name__}: {value}"
                print(f"GUI Error handled: {error_msg}")
                
                # Try to log to GUI if possible
                try:
                    self.log_message(f"⚠️ {error_msg}")
                except:
                    pass  # If logging fails, just continue
                
                # For specific widget errors, try to recover
                if "TclError" in str(exception):
                    try:
                        # Refresh the GUI to restore functionality
                        self.root.update_idletasks()
                    except:
                        pass
            
            # Set the exception handler
            self.root.report_callback_exception = handle_exception
            
            # Add a periodic health check
            self.root.after(5000, self.gui_health_check)  # Check every 5 seconds
            
        except Exception as e:
            print(f"Could not set up global error protection: {e}")
    
    def gui_health_check(self):
        """Periodic check to ensure GUI is healthy"""
        try:
            # Simple check - try to update the root window
            self.root.update_idletasks()
            
            # Schedule next check
            self.root.after(5000, self.gui_health_check)
        except Exception as e:
            print(f"GUI health check failed: {e}")
            # Try to recover by scheduling another check
            try:
                self.root.after(10000, self.gui_health_check)  # Try again in 10 seconds
            except:
                pass
    
    def load_profiles(self):
        """Load profiles from profiles.json"""
        try:
            profiles_file = os.path.join(os.path.dirname(__file__), "profiles.json")
            
            # Create empty profiles.json if it doesn't exist
            if not os.path.exists(profiles_file):
                self.profiles = {}
                with open(profiles_file, 'w', encoding='utf-8') as f:
                    json.dump(self.profiles, f, indent=2)
                print("Created empty profiles.json file")
                return
            
            with open(profiles_file, 'r', encoding='utf-8') as f:
                self.profiles = json.load(f)
        except json.JSONDecodeError as e:
            error_msg = f"JSON format error in profiles.json at line {e.lineno}, column {e.colno}: {e.msg}"
            self.log_message(f"❌ {error_msg}")
            
            # Try to create a backup and offer to reset
            backup_file = profiles_file + ".backup"
            try:
                if os.path.exists(profiles_file):
                    shutil.copy2(profiles_file, backup_file)
                    self.log_message(f"💾 Created backup: {backup_file}")
            except Exception:
                pass
            
            # Offer to reset profiles
            if hasattr(self, 'root'):
                response = messagebox.askyesno(
                    "Corrupted Profiles File", 
                    f"{error_msg}\n\n"
                    "The profiles file appears to be corrupted. This can happen if GUI callback functions were accidentally saved.\n\n"
                    "Would you like to reset to an empty profiles file? (A backup will be kept)"
                )
                if response:
                    self.profiles = {}
                    self.save_profiles()  # Save empty profiles
                    messagebox.showinfo("Reset Complete", "Profiles have been reset. You can recreate your channels manually.")
                    return
            
            # If no GUI or user declined, use empty profiles
            self.profiles = {}
            
        except Exception as e:
            error_msg = f"Failed to load profiles: {e}"
            if hasattr(self, 'log_message'):
                self.log_message(f"❌ {error_msg}")
            if hasattr(self, 'root'):
                messagebox.showerror("Error", error_msg)
            self.profiles = {}
    
    def save_profiles(self):
        """Save profiles to profiles.json and update startup batch file"""
        try:
            # First save the current profile from editor if one is selected
            if hasattr(self, 'selected_profile') and self.selected_profile:
                # Count hashtags before saving for feedback
                hashtag_count = self.hashtags_listbox.size() if hasattr(self, 'hashtags_listbox') else 0
                
                self.save_profile_from_editor()
                self.log_message(f"💾 Saved current changes for '{self.selected_profile}' ({hashtag_count} hashtags)")
            
            profiles_file = os.path.join(os.path.dirname(__file__), "profiles.json")
            
            # Clean profiles data before saving - remove any GUI callback functions
            cleaned_profiles = {}
            for name, profile in self.profiles.items():
                cleaned_profile = {}
                for key, value in profile.items():
                    # Skip any keys that start with underscore (GUI internal data)
                    if key.startswith('_'):
                        continue
                    # Skip any function objects
                    if callable(value):
                        continue
                    
                    if isinstance(value, dict):
                        # Clean nested dictionaries too
                        cleaned_dict = {}
                        for sub_key, sub_value in value.items():
                            # Skip underscore keys and functions in nested dicts too
                            if sub_key.startswith('_') or callable(sub_value):
                                continue
                            cleaned_dict[sub_key] = sub_value
                        cleaned_profile[key] = cleaned_dict
                    else:
                        cleaned_profile[key] = value
                
                cleaned_profiles[name] = cleaned_profile
            
            with open(profiles_file, 'w', encoding='utf-8') as f:
                json.dump(cleaned_profiles, f, indent=2, ensure_ascii=False)
            self.log_message("✅ All profiles saved to file successfully")
            
            # Update the startup batch file based on current profile settings
            self.update_startup_batch_file()
            
            # Show visual feedback
            if hasattr(self, 'save_indicator'):
                self.save_indicator.config(text="✅ Saved!", foreground='#00aa00')
                self.root.after(3000, lambda: self.save_indicator.config(text=""))
            
            # Reset unsaved changes flag since everything is now saved
            self.has_unsaved_changes = False
            self.has_unsaved_startup_changes = False
            self.store_original_profile_data()  # Update stored data
            self.store_original_startup_states()  # Update stored startup states
            
            # Update displays with a slight delay to ensure GUI refreshes properly
            def delayed_refresh():
                # Refresh the profile list to show any label changes
                if hasattr(self, 'refresh_profile_list'):
                    self.refresh_profile_list()
                    # Ensure the current profile remains selected
                    if hasattr(self, 'selected_profile') and self.selected_profile:
                        self.select_profile_in_list(self.selected_profile)
                
                # Update the startup display since startup settings might have changed
                if hasattr(self, 'refresh_startup_display'):
                    self.refresh_startup_display()
                
                # Update the processing tab display to reflect any changes
                if hasattr(self, 'refresh_channel_status'):
                    self.refresh_channel_status()
            
            self.root.after(100, delayed_refresh)  # 100ms delay
                
        except TypeError as e:
            if "not JSON serializable" in str(e):
                error_msg = f"JSON serialization error: {str(e)}. Some non-serializable data was cleaned automatically."
                self.log_message(f"⚠️ {error_msg}")
                # Try to identify which profile has the issue for debugging
                for name, profile in self.profiles.items():
                    try:
                        json.dumps(profile)
                    except TypeError:
                        self.log_message(f"🔍 Profile '{name}' has non-serializable data (cleaned automatically)")
            else:
                self.log_message(f"❌ Type error when saving profiles: {str(e)}")
                messagebox.showerror("Error", f"Failed to save profiles: {e}")
        except Exception as e:
            self.log_message(f"❌ Error saving profiles: {str(e)}")
            messagebox.showerror("Error", f"Failed to save profiles: {e}")
    
    def update_startup_batch_file(self):
        """Update or create/remove the startup batch file based on current startup profiles"""
        try:
            # Get startup-enabled profiles
            startup_profiles = [name for name, profile in self.profiles.items() if profile.get('run_on_startup', False)]
            
            # Get the batch file path
            startup_folder = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
            batch_file_path = os.path.join(startup_folder, 'YouTubeShortsBot.bat')
            
            if not startup_profiles:
                # No startup profiles - remove batch file if it exists
                if os.path.exists(batch_file_path):
                    os.remove(batch_file_path)
                    self.log_message("❌ Removed startup batch file (no startup channels)")
                return
            
            # Create startup folder if it doesn't exist
            os.makedirs(startup_folder, exist_ok=True)
            
            # Get paths
            script_dir = os.path.dirname(__file__)
            python_exe = sys.executable
            
            # Create the batch file content with individual channel commands
            batch_content = f'''@echo off
REM YouTube Shorts Bot Startup Script
REM This script runs selected channels marked for startup
REM Generated automatically by YouTube Shorts Bot Manager

echo Starting YouTube Shorts Bot for {len(startup_profiles)} channel(s)...
cd /d "{script_dir}"

'''
            
            # Add commands for each startup channel, respecting daily upload limits
            total_uploads = 0
            for profile_name in startup_profiles:
                profile = self.profiles[profile_name]
                daily_limit = profile.get('daily_upload_limit', 1)
                total_uploads += daily_limit
                
                batch_content += f'''REM Processing channel: {profile_name} ({daily_limit} upload(s))
'''
                
                # Add multiple calls for channels with daily_upload_limit > 1
                for upload_num in range(daily_limit):
                    batch_content += f'''echo Processing {profile_name} - Upload {upload_num + 1}/{daily_limit}...
"{python_exe}" "process_videos.py" "{profile_name}"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to process {profile_name} upload {upload_num + 1}
) else (
    echo SUCCESS: {profile_name} upload {upload_num + 1} processed successfully
)
echo.

'''
            
            # Add completion message with total upload count
            batch_content += f'''echo Startup processing completed for all {len(startup_profiles)} channels ({total_uploads} total uploads).
REM Uncomment the line below if you want to see the output window
REM pause
'''
            
            # Write the batch file
            with open(batch_file_path, 'w') as f:
                f.write(batch_content)
            
            # Calculate total uploads for logging
            total_uploads = sum(self.profiles[name].get('daily_upload_limit', 1) for name in startup_profiles)
            upload_summary = ", ".join([f"{name}({self.profiles[name].get('daily_upload_limit', 1)})" for name in startup_profiles])
            
            self.log_message(f"✅ Updated startup batch file with {len(startup_profiles)} channel(s), {total_uploads} total uploads: {upload_summary}")
            
        except Exception as e:
            self.log_message(f"❌ Error updating startup batch file: {str(e)}")
            # Don't show error dialog here since this is called from save_profiles
    
    def check_storage_space(self):
        """Check if there's enough disk space and show warning if low"""
        try:
            # Get disk usage for the current directory
            project_path = os.path.dirname(__file__)
            total, used, free = shutil.disk_usage(project_path)
            
            # Convert to GB
            free_gb = free / (1024**3)
            
            # Show warning if less than 2GB free
            if free_gb < 2.0:
                self.show_storage_warning(free_gb)
            else:
                self.hide_storage_warning()
            
            # Store the state for later use if GUI isn't ready yet
            self._storage_insufficient = free_gb < 2.0
            
        except Exception as e:
            # If we can't check storage, assume it's okay to avoid false alarms
            self.hide_storage_warning()
            self._storage_insufficient = False
    
    def show_storage_warning(self, free_gb):
        """Show warning banner for insufficient storage space"""
        # Check if storage_warning_frame exists and notebook exists
        if not hasattr(self, 'storage_warning_frame') or not hasattr(self, 'notebook'):
            return
        
        # If warning is already shown, don't show it again
        if self._storage_warning_shown:
            return
        
        # Clear existing content
        for widget in self.storage_warning_frame.winfo_children():
            widget.destroy()
        
        # Create modern warning banner
        warning_content = ttk.Frame(self.storage_warning_frame, style='Warning.TFrame', padding=15)
        warning_content.pack(fill=tk.X)
        
        # Left side - warning icon and text
        left_frame = ttk.Frame(warning_content, style='Warning.TFrame')
        left_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Warning icon and main text
        header_frame = ttk.Frame(left_frame, style='Warning.TFrame')
        header_frame.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Label(header_frame, text="💾", font=('Segoe UI', 16), style='Warning.TLabel').pack(side=tk.LEFT, padx=(0, 10))
        
        text_frame = ttk.Frame(header_frame, style='Warning.TFrame')
        text_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Label(text_frame, text="⚠️ Low Disk Space Warning", 
                 font=('Segoe UI', 12, 'bold'), style='Warning.TLabel').pack(anchor=tk.W)
        ttk.Label(text_frame, text=f"Only {free_gb:.1f} GB free space available. Video processing may fail with insufficient storage.", 
                 font=('Segoe UI', 10), style='Warning.TLabel').pack(anchor=tk.W)
        
        # Right side - action buttons
        warning_buttons = ttk.Frame(warning_content, style='Warning.TFrame')
        warning_buttons.pack(side=tk.RIGHT, padx=(20, 0))
        
        ttk.Button(warning_buttons, text="📁 Open Project Folder", 
                  command=self.open_project_folder, style="TButton").pack(side=tk.RIGHT, padx=(0, 5))
        ttk.Button(warning_buttons, text="🔄 Recheck", 
                  command=self.check_storage_space, style="TButton").pack(side=tk.RIGHT)
        
        # Show the warning frame - use grid at row 4 (after other warnings)
        self.storage_warning_frame.grid(row=4, column=0, sticky="ew", pady=(0, 15))
        
        # Update main status if no higher priority warnings are shown
        if hasattr(self, 'main_status') and not (self._warning_shown or self._reddit_warning_shown):
            self.main_status.config(text="⚠️ Setup Required", foreground='#ff6600')
        
        # Configure warning style
        style = ttk.Style()
        style.configure('Warning.TFrame', background='#fff3cd', relief='solid', borderwidth=1)
        style.configure('Warning.TLabel', background='#fff3cd', foreground='#856404')
        
        # Mark warning as shown
        self._storage_warning_shown = True
    
    def hide_storage_warning(self):
        """Hide the storage space warning banner"""
        try:
            if hasattr(self, 'storage_warning_frame') and self.storage_warning_frame.winfo_viewable():
                self.storage_warning_frame.grid_forget()
                
                # Clear warning frame contents
                for widget in self.storage_warning_frame.winfo_children():
                    widget.destroy()
                
                # Reset main status only if no other warnings are shown
                if hasattr(self, 'main_status') and not (self._warning_shown or self._reddit_warning_shown):
                    self.main_status.config(text="● Ready", foreground='#00aa00')
            
            # Reset warning flag
            self._storage_warning_shown = False
                    
        except AttributeError:
            # storage_warning_frame doesn't exist yet, that's fine
            pass
        except tk.TclError:
            # widget was already destroyed, that's fine
            pass
    
    def cached_file_exists(self, filepath):
        """Check file existence with caching to reduce I/O operations."""
        import time
        current_time = time.time()
        
        # Check if we have a cached result that's less than 30 seconds old
        if filepath in self._file_cache and filepath in self._cache_expiry:
            if current_time - self._cache_expiry[filepath] < 30:
                return self._file_cache[filepath]
        
        # Check file existence and cache the result
        exists = os.path.exists(filepath)
        self._file_cache[filepath] = exists
        self._cache_expiry[filepath] = current_time
        return exists

    def _configure_common_styles(self):
        """Pre-configure common widget styles to improve performance."""
        try:
            # Cache common style configurations
            self.style.configure('Header.TLabel', font=('Arial', 10, 'bold'))
            self.style.configure('Warning.TLabel', foreground='red', font=('Arial', 9))
            self.style.configure('Success.TLabel', foreground='green', font=('Arial', 9))
            self.style.configure('Small.TLabel', font=('Arial', 8))
            self.style.configure('Compact.TButton', padding=(2, 2))
        except Exception:
            # If styling fails, continue without it
            pass
    
    def check_client_secrets(self):
        """Check if client_secrets.json exists and show warning if missing"""
        client_secrets_path = os.path.join(os.path.dirname(__file__), "client_secrets.json")
        print(f"DEBUG: Looking for client_secrets.json at: {client_secrets_path}")
        
        file_exists = self.cached_file_exists(client_secrets_path)
        print(f"DEBUG: client_secrets.json exists: {file_exists}")
        
        if not file_exists:
            print("DEBUG: File missing, showing warning...")
            self.show_client_secrets_warning()
        else:
            print("DEBUG: File exists, hiding warning...")
            self.hide_client_secrets_warning()
        
        # Store the state for later use if GUI isn't ready yet
        self._client_secrets_missing = not os.path.exists(client_secrets_path)
    
    def show_client_secrets_warning(self):
        """Show warning banner for missing client_secrets.json"""
        print("DEBUG: show_client_secrets_warning called")
        
        # Check if warning_frame exists and notebook exists
        if not hasattr(self, 'warning_frame') or not hasattr(self, 'notebook'):
            print("DEBUG: Warning frame or notebook doesn't exist yet, returning")
            return
        
        print(f"DEBUG: warning_frame exists: {hasattr(self, 'warning_frame')}")
        print(f"DEBUG: notebook exists: {hasattr(self, 'notebook')}")
        
        # If warning is already shown, don't show it again
        if hasattr(self, '_warning_shown') and self._warning_shown:
            print("DEBUG: Warning already shown, returning")
            return
        
        print("DEBUG: Creating warning content...")
        
        # Ensure notebook is properly packed before proceeding
        try:
            # Force update to ensure notebook is packed
            self.root.update_idletasks()
            print(f"DEBUG: Notebook winfo_manager: {self.notebook.winfo_manager()}")
        except Exception as e:
            print(f"DEBUG: Error checking notebook state: {e}")
        
        # Clear any existing warning content first
        for widget in self.warning_frame.winfo_children():
            widget.destroy()
        
        # Configure warning frame
        self.warning_frame.configure(style='Warning.TFrame')
        
        # Create warning content
        warning_content = ttk.Frame(self.warning_frame)
        warning_content.pack(fill=tk.X, padx=15, pady=10)
        
        # Warning icon and text
        warning_left = ttk.Frame(warning_content)
        warning_left.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Label(warning_left, text="⚠️", font=('Segoe UI', 16), foreground='#ff6600').pack(side=tk.LEFT, padx=(0, 10))
        
        warning_text_frame = ttk.Frame(warning_left)
        warning_text_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Label(warning_text_frame, text="Missing client_secrets.json - Required for YouTube token generation", 
                 font=('Segoe UI', 12, 'bold'), foreground='#ff6600').pack(anchor=tk.W)
        ttk.Label(warning_text_frame, text="Video processing is disabled until this file is configured. Click ' Setup Guide' for instructions.", 
                 font=('Segoe UI', 10), foreground='#cc5500').pack(anchor=tk.W)
        
        # Action buttons
        warning_buttons = ttk.Frame(warning_content)
        warning_buttons.pack(side=tk.RIGHT, padx=(10, 0))
        
        ttk.Button(warning_buttons, text="📁 Browse & Copy File", 
                  command=self.browse_client_secrets_for_banner, style="TButton").pack(side=tk.RIGHT, padx=(0, 5))
        ttk.Button(warning_buttons, text="📖 Setup Guide", 
                  command=self.show_client_secrets_guide, style="TButton").pack(side=tk.RIGHT)
        
        # Show the warning frame
        try:
            # Use grid instead of pack since the parent uses grid
            # Insert warning at row 2 (between tabs_header and notebook)
            self.warning_frame.grid(row=2, column=0, sticky="ew", pady=(0, 15))
            print("DEBUG: Warning frame gridded at row 2")
        except tk.TclError as e:
            print(f"DEBUG: Failed to grid warning frame: {e}")
        
        # Update main status
        if hasattr(self, 'main_status'):
            self.main_status.config(text="⚠️ Setup Required", foreground='#ff6600')
        
        # Configure warning style
        style = ttk.Style()
        style.configure('Warning.TFrame', background='#fff3cd', relief='solid', borderwidth=1)
        
        # Mark warning as shown
        self._warning_shown = True
        print("DEBUG: Warning marked as shown")
    
    def hide_client_secrets_warning(self):
        """Hide the client_secrets.json warning banner"""
        # Check if warning_frame exists and is viewable
        try:
            if hasattr(self, 'warning_frame') and self.warning_frame.winfo_viewable():
                self.warning_frame.grid_forget()
                
                # Clear warning frame contents
                for widget in self.warning_frame.winfo_children():
                    widget.destroy()
                
                # Reset main status only if no other warnings are shown
                if hasattr(self, 'main_status') and not (self._reddit_warning_shown or self._storage_warning_shown):
                    self.main_status.config(text="● Ready", foreground='#00aa00')
            
            # Reset warning flag
            self._warning_shown = False
                    
        except AttributeError:
            # warning_frame doesn't exist yet, that's fine
            pass
        except tk.TclError:
            # widget was already destroyed, that's fine
            pass
    
    def refresh_client_secrets_check(self):
        """Refresh client secrets check without duplicating warning"""
        # Reset the warning flag and clear existing warning
        self._warning_shown = False
        self.hide_client_secrets_warning()
        # Now check again
        self.check_client_secrets()
    
    def browse_client_secrets_for_banner(self):
        """Browse and copy client_secrets.json from the warning banner"""
        try:
            source_file = filedialog.askopenfilename(
                title="Select downloaded client_secrets.json file",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialdir=os.path.expanduser("~/Downloads")  # Start in Downloads folder
            )
            
            if not source_file:  # User cancelled
                return
            
            # Check if it's actually named client_secrets.json or similar
            filename = os.path.basename(source_file)
            if 'client' not in filename.lower() or not filename.endswith('.json'):
                if not messagebox.askyesno("File Name Warning", 
                                         f"Selected file: {filename}\n\n"
                                         "This doesn't look like a client_secrets.json file.\n"
                                         "Continue anyway?"):
                    return
            
            # Copy to the correct location
            target_path = os.path.join(os.path.dirname(__file__), "client_secrets.json")
            
            try:
                shutil.copy2(source_file, target_path)
                self.log_message(f"✅ Copied {filename} to client_secrets.json")
                
                # Recheck and hide warning banner
                self.check_client_secrets()
                
                messagebox.showinfo("Success!", 
                                  f"✅ client_secrets.json has been copied successfully!\n\n"
                                  f"From: {source_file}\n"
                                  f"To: {target_path}\n\n"
                                  "You can now create new YouTube channel profiles.")
                
            except Exception as e:
                messagebox.showerror("Copy Error", f"Failed to copy file: {str(e)}")
                
        except Exception as e:
            messagebox.showerror("Browse Error", f"Failed to browse for file: {str(e)}")

    def show_client_secrets_guide(self):
        """Show detailed guide for obtaining client_secrets.json"""
        dialog = tk.Toplevel(self.root)
        dialog.title(" Setup Guide: client_secrets.json")
        dialog.geometry("700x600")
        dialog.configure(bg='#f8f9fa')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Create scrollable content
        canvas = tk.Canvas(dialog, bg='#f8f9fa', highlightthickness=0)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Title
        ttk.Label(scrollable_frame, text="🔧 YouTube API  Setup Guide", 
                 font=('Segoe UI', 16, 'bold')).pack(pady=(20, 10))
        
        ttk.Label(scrollable_frame, text="Follow these steps to obtain the client_secrets.json file:", 
                 font=('Segoe UI', 12)).pack(pady=(0, 20))
        
        # Step-by-step instructions
        steps = [
            ("1. Create Google Cloud Project", [
                "• Go to console.cloud.google.com",
                "• Click 'New Project' or select existing project",
                "• Give it a name like 'YouTube Shorts Bot'"
            ]),
            ("2. Enable YouTube Data API v3", [
                "• Go to APIs & Services → Library",
                "• Search for 'YouTube Data API v3'",
                "• Click on it and press 'Enable'"
            ]),
            ("3. Configure OAuth Consent Screen", [
                "• Go to APIs & Services → OAuth consent screen",
                "• Choose 'External' (unless you have G Suite)",
                "• Fill in App name: 'YouTube Shorts Bot'",
                "• Add your email as developer contact",
                "• Save and continue through the steps"
            ]),
            ("4. Create OAuth 2.0 Credentials", [
                "• Go to APIs & Services → Credentials",
                "• Click '+ CREATE CREDENTIALS' → 'OAuth client ID'",
                "• Application type: 'Desktop application'",
                "• Name: 'YouTube Shorts Bot Client'",
                "• Click 'Create'"
            ]),
            ("5. Download client_secrets.json", [
                "• After creating, click 'DOWNLOAD JSON'",
                "• The file will download (usually to Downloads folder)",
                "• Click ' Browse & Copy File' button below to automatically",
                "  find and copy it to the correct location",
                "• OR manually save/rename as 'client_secrets.json' in:",
                f"  {os.path.dirname(__file__)}",
                "• DO NOT rename or modify the file contents"
            ])
        ]
        
        for step_title, step_items in steps:
            # Step header
            step_frame = ttk.LabelFrame(scrollable_frame, text=step_title, padding=15)
            step_frame.pack(fill=tk.X, padx=20, pady=10)
            
            for item in step_items:
                ttk.Label(step_frame, text=item, font=('Segoe UI', 10)).pack(anchor=tk.W, pady=2)
        
        # Important notes
        notes_frame = ttk.LabelFrame(scrollable_frame, text="⚠️ Important Notes", padding=15)
        notes_frame.pack(fill=tk.X, padx=20, pady=10)
        
        notes = [
            "• Keep client_secrets.json SECRET - never share publicly",
            "• One file works for ALL your YouTube channels",
            "• Each channel gets its own token after first authentication",
            "• You'll sign into each channel separately during setup"
        ]
        
        for note in notes:
            ttk.Label(notes_frame, text=note, font=('Segoe UI', 10), foreground='#cc5500').pack(anchor=tk.W, pady=2)
        
        # Action buttons
        button_frame = ttk.Frame(scrollable_frame)
        button_frame.pack(fill=tk.X, padx=20, pady=20)
        
        def open_google_console():
            import webbrowser
            webbrowser.open('https://console.cloud.google.com/')
            self.log_message("🌐 Opened Google Cloud Console in browser")
        
        def copy_folder_path():
            folder_path = os.path.dirname(__file__)
            self.root.clipboard_clear()
            self.root.clipboard_append(folder_path)
            self.log_message(f"📋 Copied folder path: {folder_path}")
        
        def browse_and_copy_secrets():
            """Let user browse for downloaded client_secrets.json and copy it to the right location"""
            try:
                source_file = filedialog.askopenfilename(
                    title="Select downloaded client_secrets.json file",
                    filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                    initialdir=os.path.expanduser("~/Downloads")  # Start in Downloads folder
                )
                
                if not source_file:  # User cancelled
                    return
                
                # Check if it's actually named client_secrets.json or similar
                filename = os.path.basename(source_file)
                if 'client' not in filename.lower() or not filename.endswith('.json'):
                    if not messagebox.askyesno("File Name Warning", 
                                             f"Selected file: {filename}\n\n"
                                             "This doesn't look like a client_secrets.json file.\n"
                                             "Continue anyway?"):
                        return
                
                # Copy to the correct location
                target_path = os.path.join(os.path.dirname(__file__), "client_secrets.json")
                
                try:
                    shutil.copy2(source_file, target_path)
                    self.log_message(f"✅ Copied {filename} to client_secrets.json")
                    
                    # Close dialog and recheck
                    dialog.destroy()
                    self.check_client_secrets()
                    
                    messagebox.showinfo("Success!", 
                                      f"✅ client_secrets.json has been copied successfully!\n\n"
                                      f"From: {source_file}\n"
                                      f"To: {target_path}\n\n"
                                      "You can now create new YouTube channel profiles.")
                    
                except Exception as e:
                    messagebox.showerror("Copy Error", f"Failed to copy file: {str(e)}")
                    
            except Exception as e:
                messagebox.showerror("Browse Error", f"Failed to browse for file: {str(e)}")
        
        ttk.Button(button_frame, text="🌐 Open Google Cloud Console", 
                  command=open_google_console, style="TButton").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="📁  Browse & Copy File", 
                  command=browse_and_copy_secrets, style="TButton").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="📋 Copy Folder Path", 
                  command=copy_folder_path, style="TButton").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="🔄 Check Again", 
                  command=lambda: [dialog.destroy(), self.check_client_secrets()], style="TButton").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="❌ Close", 
                  command=dialog.destroy, style="TButton").pack(side=tk.RIGHT)
        
        # Pack scrollable content
        canvas.pack(side="left", fill="both", expand=True, padx=(20, 0), pady=20)
        scrollbar.pack(side="right", fill="y", pady=20)
        
        # Bind mousewheel
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind("<MouseWheel>", _on_mousewheel)
    
    def check_client_secrets_exists(self):
        """Check if client_secrets.json exists (helper method)"""
        client_secrets_path = os.path.join(os.path.dirname(__file__), "client_secrets.json")
        return os.path.exists(client_secrets_path)
    
    def check_reddit_config(self):
        """Check if Reddit API configuration is properly set up"""
        try:
            # Force reload config module to get fresh values
            import importlib
            import config
            importlib.reload(config)
            
            # Default placeholder values to check against
            default_client_id = "your_reddit_client_id_here"
            default_client_secret = "your_reddit_client_secret_here"  
            default_user_agent = "your-app-name/1.0 by u/yourusername"
            
            # Check if Reddit credentials are still the default placeholders or empty
            is_default_or_empty = (
                config.REDDIT_CLIENT_ID == default_client_id or 
                config.REDDIT_CLIENT_SECRET == default_client_secret or
                config.REDDIT_USER_AGENT == default_user_agent or
                not config.REDDIT_CLIENT_ID or 
                not config.REDDIT_CLIENT_SECRET or 
                not config.REDDIT_USER_AGENT or
                config.REDDIT_CLIENT_ID.strip() == "" or
                config.REDDIT_CLIENT_SECRET.strip() == "" or
                config.REDDIT_USER_AGENT.strip() == ""
            )
            
            # Debug logging (only if log_text exists)
            if hasattr(self, 'log_text'):
                self.log_message(f"🔍 Reddit Config Check:")
                self.log_message(f"  Client ID: '{config.REDDIT_CLIENT_ID}' (Default: {config.REDDIT_CLIENT_ID == default_client_id})")
                self.log_message(f"  Client Secret: '{config.REDDIT_CLIENT_SECRET}' (Default: {config.REDDIT_CLIENT_SECRET == default_client_secret})")
                self.log_message(f"  User Agent: '{config.REDDIT_USER_AGENT}' (Default: {config.REDDIT_USER_AGENT == default_user_agent})")
                self.log_message(f"  Is Default or Empty: {is_default_or_empty}")
            
            if is_default_or_empty:
                self.show_reddit_config_warning()
                self._reddit_config_missing = True
                if hasattr(self, 'log_text'):
                    self.log_message("⚠️ Showing Reddit API warning - configuration needed")
            else:
                self.hide_reddit_config_warning()
                self._reddit_config_missing = False
                if hasattr(self, 'log_text'):
                    self.log_message("✅ Reddit API configuration is properly set up")
                
        except Exception as e:
            # If config can't be imported or has issues, show warning
            if hasattr(self, 'log_text'):
                self.log_message(f"❌ Error checking Reddit config: {str(e)}")
            self.show_reddit_config_warning()
            self._reddit_config_missing = True
    
    def show_reddit_config_warning(self):
        """Show warning banner for missing Reddit API configuration"""
        # Check if reddit_warning_frame exists and notebook exists
        if not hasattr(self, 'reddit_warning_frame') or not hasattr(self, 'notebook'):
            return
        
        # If warning is already shown, don't show it again
        if hasattr(self, '_reddit_warning_shown') and self._reddit_warning_shown:
            return
        
        # Clear any existing warning content first
        for widget in self.reddit_warning_frame.winfo_children():
            widget.destroy()
        
        # Configure warning frame - use same style as client_secrets warning
        self.reddit_warning_frame.configure(style='Warning.TFrame')
        
        # Create warning content
        warning_content = ttk.Frame(self.reddit_warning_frame)
        warning_content.pack(fill=tk.X, padx=15, pady=10)
        
        # Warning icon and text
        warning_left = ttk.Frame(warning_content)
        warning_left.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Label(warning_left, text="⚠️", font=('Segoe UI', 16), foreground='#ff6600').pack(side=tk.LEFT, padx=(0, 10))
        
        warning_text_frame = ttk.Frame(warning_left)
        warning_text_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Label(warning_text_frame, text="Missing Reddit API configuration - Required for fetching subreddit content", 
                 font=('Segoe UI', 12, 'bold'), foreground='#ff6600').pack(anchor=tk.W)
        ttk.Label(warning_text_frame, text="Video processing is disabled until Reddit credentials are configured. Click 'Setup Guide' for instructions.", 
                 font=('Segoe UI', 10), foreground='#cc5500').pack(anchor=tk.W)
        
        # Action buttons
        warning_buttons = ttk.Frame(warning_content)
        warning_buttons.pack(side=tk.RIGHT, padx=(10, 0))
        
        ttk.Button(warning_buttons, text="⚙️ Configure Reddit API", 
                  command=self.show_reddit_config_dialog, style="Accent.TButton").pack(side=tk.RIGHT, padx=(0, 5))
        ttk.Button(warning_buttons, text="📖 Setup Guide", 
                  command=self.show_reddit_setup_guide, style="TButton").pack(side=tk.RIGHT, padx=(0, 5))
        ttk.Button(warning_buttons, text="🔄 Recheck", 
                  command=self.refresh_reddit_config_check, style="TButton").pack(side=tk.RIGHT)
        
        # Show the warning frame - use grid at row 3 (after client_secrets warning)
        self.reddit_warning_frame.grid(row=3, column=0, sticky="ew", pady=(0, 15))
        
        # Update main status if no client_secrets warning is shown
        if hasattr(self, 'main_status') and not self._warning_shown:
            self.main_status.config(text="⚠️ Setup Required", foreground='#ff6600')
        
        # Configure warning style (same as client_secrets)
        style = ttk.Style()
        style.configure('Warning.TFrame', background='#fff3cd', relief='solid', borderwidth=1)
        
        # Mark warning as shown
        self._reddit_warning_shown = True
    
    def hide_reddit_config_warning(self):
        """Hide the Reddit API configuration warning banner"""
        try:
            if hasattr(self, 'reddit_warning_frame') and self.reddit_warning_frame.winfo_viewable():
                self.reddit_warning_frame.grid_forget()
                
                # Clear warning frame contents
                for widget in self.reddit_warning_frame.winfo_children():
                    widget.destroy()
                
                # Reset main status only if no other warnings are shown
                if hasattr(self, 'main_status') and not (self._warning_shown or self._storage_warning_shown):
                    self.main_status.config(text="● Ready", foreground='#00aa00')
            
            # Reset warning flag
            self._reddit_warning_shown = False
                    
        except AttributeError:
            # reddit_warning_frame doesn't exist yet, that's fine
            pass
        except tk.TclError:
            # widget was already destroyed, that's fine
            pass
    
    def show_reddit_config_dialog(self):
        """Show dialog for configuring Reddit API credentials"""
        dialog = tk.Toplevel(self.root)
        dialog.title("🔧 Reddit API Configuration")
        dialog.geometry("600x500")
        dialog.configure(bg='#f8f9fa')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Main frame
        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Title
        ttk.Label(main_frame, text="🔧 Configure Reddit API", 
                 font=('Segoe UI', 16, 'bold')).pack(pady=(0, 20))
        
        # Load current config values
        try:
            import config
            current_client_id = config.REDDIT_CLIENT_ID
            current_client_secret = config.REDDIT_CLIENT_SECRET
            current_user_agent = config.REDDIT_USER_AGENT
        except:
            current_client_id = ""
            current_client_secret = ""
            current_user_agent = ""
        
        # If values are still defaults, clear them for better UX
        if current_client_id == "your_reddit_client_id_here":
            current_client_id = ""  # Clear default so user can see placeholder
        if current_client_secret == "your_reddit_client_secret_here":
            current_client_secret = ""  # Clear default so user can see placeholder
        if current_user_agent == "your-app-name/1.0 by u/yourusername":
            current_user_agent = ""  # Clear default completely for auto-generation
        
        # Input fields
        fields_frame = ttk.LabelFrame(main_frame, text="Reddit API Credentials", padding=15)
        fields_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Client ID
        ttk.Label(fields_frame, text="Client ID:", font=('Segoe UI', 10, 'bold')).pack(anchor=tk.W, pady=(0, 5))
        client_id_var = tk.StringVar(value=current_client_id)
        client_id_entry = ttk.Entry(fields_frame, textvariable=client_id_var, font=('Segoe UI', 10), width=50)
        client_id_entry.pack(fill=tk.X, pady=(0, 10))
        
        # Client Secret
        ttk.Label(fields_frame, text="Client Secret:", font=('Segoe UI', 10, 'bold')).pack(anchor=tk.W, pady=(0, 5))
        client_secret_var = tk.StringVar(value=current_client_secret)
        client_secret_entry = ttk.Entry(fields_frame, textvariable=client_secret_var, font=('Segoe UI', 10), width=50, show="*")
        client_secret_entry.pack(fill=tk.X, pady=(0, 10))
        
        # User Agent - simplified with auto-generation
        ttk.Label(fields_frame, text="User Agent:", font=('Segoe UI', 10, 'bold')).pack(anchor=tk.W, pady=(0, 5))
        
        user_agent_frame = ttk.Frame(fields_frame)
        user_agent_frame.pack(fill=tk.X, pady=(5, 0))
        
        user_agent_var = tk.StringVar(value=current_user_agent)
        user_agent_entry = ttk.Entry(user_agent_frame, textvariable=user_agent_var, font=('Segoe UI', 10))
        user_agent_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        def auto_generate_user_agent():
            # Simple dialog to get just the username
            self._dialog_open = True
            username = tk.simpledialog.askstring(
                "Auto-Generate User Agent", 
                "Enter your Reddit username (without u/):",
                initialvalue=""
            )
            self._dialog_open = False
            
            if username:
                if username.startswith('u/'):
                    username = username[2:]  # Remove u/ if user included it
                auto_agent = f"youtube-shorts-bot/1.0 by u/{username}"
                user_agent_var.set(auto_agent)
        
        ttk.Button(user_agent_frame, text="🔧 Auto-Generate", 
                  command=auto_generate_user_agent, style="TButton").pack(side=tk.RIGHT)
        
        # Simple help text
        ttk.Label(fields_frame, text="User Agent identifies your bot to Reddit. Click 'Auto-Generate' for easy setup.", 
                 font=('Segoe UI', 9), foreground='gray').pack(anchor=tk.W, pady=(5, 10))
        
        # Add placeholder text when fields are empty
        def add_placeholder(entry, placeholder_text):
            def on_focus_in(event):
                if entry.get() == placeholder_text:
                    entry.delete(0, tk.END)
                    entry.config(foreground='black')
            
            def on_focus_out(event):
                if entry.get() == "":
                    entry.insert(0, placeholder_text)
                    entry.config(foreground='gray')
            
            if entry.get() == "":
                entry.insert(0, placeholder_text)
                entry.config(foreground='gray')
            
            entry.bind('<FocusIn>', on_focus_in)
            entry.bind('<FocusOut>', on_focus_out)
        
        # Add placeholders if fields are empty
        if not current_client_id:
            add_placeholder(client_id_entry, "Enter your Reddit app Client ID")
        if not current_client_secret:
            add_placeholder(client_secret_entry, "Enter your Reddit app Client Secret")
        if current_user_agent == "youtube-shorts-bot/1.0 by u/yourusername":
            add_placeholder(user_agent_entry, "youtube-shorts-bot/1.0 by u/yourusername")
        
        # Status label
        status_label = ttk.Label(main_frame, text="", font=('Segoe UI', 10))
        status_label.pack(pady=(10, 0))
        
        def save_config():
            try:
                client_id = client_id_var.get().strip()
                client_secret = client_secret_var.get().strip()
                user_agent = user_agent_var.get().strip()
                
                # Remove placeholder text if it wasn't changed
                if client_id == "Enter your Reddit app Client ID":
                    client_id = ""
                if client_secret == "Enter your Reddit app Client Secret":
                    client_secret = ""
                if user_agent == "youtube-shorts-bot/1.0 by u/yourusername":
                    user_agent = ""
                
                if not client_id or not client_secret or not user_agent:
                    status_label.config(text="❌ All fields are required (use Auto-Generate for User Agent)", foreground='red')
                    return
                
                # Validate user agent format - more lenient
                if len(user_agent.strip()) < 10:
                    status_label.config(text="❌ User Agent too short (click Auto-Generate for help)", foreground='red')
                    return
                
                # Just check for basic format, don't be too strict
                if ' by u/' not in user_agent.lower():
                    result = messagebox.askyesno(
                        "User Agent Format", 
                        f"User Agent: {user_agent}\n\n"
                        "This doesn't include 'by u/username' which Reddit recommends.\n\n"
                        "Continue anyway, or click 'No' to fix it?"
                    )
                    if not result:
                        return
                
                # Read current config file
                config_path = os.path.join(os.path.dirname(__file__), "config.py")
                with open(config_path, 'r') as f:
                    content = f.read()
                
                # Replace the values
                import re
                content = re.sub(r'REDDIT_CLIENT_ID\s*=\s*"[^"]*"', f'REDDIT_CLIENT_ID     = "{client_id}"', content)
                content = re.sub(r'REDDIT_CLIENT_SECRET\s*=\s*"[^"]*"', f'REDDIT_CLIENT_SECRET = "{client_secret}"', content)
                content = re.sub(r'REDDIT_USER_AGENT\s*=\s*"[^"]*"', f'REDDIT_USER_AGENT    = "{user_agent}"', content)
                
                # Write back to config file
                with open(config_path, 'w') as f:
                    f.write(content)
                
                status_label.config(text="✅ Configuration saved successfully!", foreground='green')
                self.log_message("✅ Reddit API configuration updated successfully")
                
                # Refresh the Reddit config check
                self.refresh_reddit_config_check()
                
                # Close dialog after a short delay
                dialog.after(1500, dialog.destroy)
                
            except Exception as e:
                status_label.config(text=f"❌ Error saving configuration: {str(e)}", foreground='red')
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(20, 0))
        
        ttk.Button(button_frame, text="📖 Setup Guide", 
                  command=lambda: [dialog.destroy(), self.show_reddit_setup_guide()], style="TButton").pack(side=tk.LEFT)
        ttk.Button(button_frame, text="❌ Cancel", 
                  command=dialog.destroy, style="Danger.TButton").pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="💾 Save Configuration", 
                  command=save_config, style="Accent.TButton").pack(side=tk.RIGHT)
    
    def show_reddit_setup_guide(self):
        """Show detailed guide for obtaining Reddit API credentials"""
        dialog = tk.Toplevel(self.root)
        dialog.title("📖 Reddit API Setup Guide")
        dialog.geometry("700x600")
        dialog.configure(bg='#f8f9fa')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Create scrollable content
        canvas = tk.Canvas(dialog, bg='#f8f9fa', highlightthickness=0)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Title
        ttk.Label(scrollable_frame, text="📖 Reddit API Setup Guide", 
                 font=('Segoe UI', 16, 'bold')).pack(pady=(20, 10))
        
        ttk.Label(scrollable_frame, text="Follow these steps to obtain Reddit API credentials:", 
                 font=('Segoe UI', 12)).pack(pady=(0, 20))
        
        # Step-by-step instructions
        steps = [
            ("1. Visit Reddit App Preferences", [
                "• Go to reddit.com and log into your account",
                "• Navigate to reddit.com/prefs/apps",
                "• Or go to User Settings → Privacy & Security → App Authorization"
            ]),
            ("2. Create a New App", [
                "• Click 'Create App' or 'Create Another App'",
                "• Choose 'script' as the app type",
                "• Fill in the form:",
                "  - Name: YouTube Shorts Bot (or any name you prefer)",
                "  - Description: Automated video creation bot",
                "  - Redirect URI: http://localhost:8080 (required but not used)"
            ]),
            ("3. Get Your Credentials", [
                "• After creating, you'll see your app listed",
                "• Client ID: The string under the app name (looks like: abc123def456)",
                "• Client Secret: Click 'edit' to reveal the secret key",
                "• Copy both values - you'll need them for configuration"
            ]),
            ("4. Create User Agent", [
                "• Format: appname/version by u/yourusername",
                "• Example: youtube-shorts-bot/1.0 by u/myusername",
                "• Replace 'myusername' with your actual Reddit username",
                "• This identifies your bot to Reddit's API"
            ]),
            ("5. Configure in the Bot", [
                "• Click 'Configure Reddit API' button",
                "• Paste your Client ID and Client Secret",
                "• Enter your User Agent string",
                "• Click 'Save Configuration' to update config.py"
            ])
        ]
        
        for step_title, step_items in steps:
            # Step header
            step_frame = ttk.LabelFrame(scrollable_frame, text=step_title, padding=15)
            step_frame.pack(fill=tk.X, padx=20, pady=10)
            
            for item in step_items:
                ttk.Label(step_frame, text=item, font=('Segoe UI', 10)).pack(anchor=tk.W, pady=2)
        
        # Important notes
        notes_frame = ttk.LabelFrame(scrollable_frame, text="⚠️ Important Notes", padding=15)
        notes_frame.pack(fill=tk.X, padx=20, pady=10)
        
        notes = [
            "• Keep your Client Secret private - never share it publicly",
            "• Reddit API has rate limits - the bot respects these automatically",
            "• Your Reddit account should be in good standing",
            "• Use a descriptive User Agent to identify your bot"
        ]
        
        for note in notes:
            ttk.Label(notes_frame, text=note, font=('Segoe UI', 10), foreground='#cc5500').pack(anchor=tk.W, pady=2)
        
        # Action buttons
        button_frame = ttk.Frame(scrollable_frame)
        button_frame.pack(fill=tk.X, padx=20, pady=20)
        
        def open_reddit_apps():
            import webbrowser
            webbrowser.open('https://reddit.com/prefs/apps')
            self.log_message("🌐 Opened Reddit App Preferences in browser")
        
        ttk.Button(button_frame, text="🌐 Open Reddit Apps", 
                  command=open_reddit_apps, style="TButton").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="❌ Close", 
                  command=dialog.destroy, style="TButton").pack(side=tk.RIGHT)
        
        # Pack scrollable content
        canvas.pack(side="left", fill="both", expand=True, padx=(20, 0), pady=20)
        scrollbar.pack(side="right", fill="y", pady=20)
        
        # Bind mousewheel
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind("<MouseWheel>", _on_mousewheel)
    
    def refresh_reddit_config_check(self):
        """Refresh Reddit config check without flickering"""
        try:
            # Force clear any cached config module
            import sys
            if 'config' in sys.modules:
                del sys.modules['config']
            
            import config
            
            # Default placeholder values to check against
            default_client_id = "your_reddit_client_id_here"
            default_client_secret = "your_reddit_client_secret_here"  
            default_user_agent = "your-app-name/1.0 by u/yourusername"
            
            # Check if Reddit credentials are still the default placeholders or empty
            is_default_or_empty = (
                config.REDDIT_CLIENT_ID == default_client_id or 
                config.REDDIT_CLIENT_SECRET == default_client_secret or
                config.REDDIT_USER_AGENT == default_user_agent or
                not config.REDDIT_CLIENT_ID or 
                not config.REDDIT_CLIENT_SECRET or 
                not config.REDDIT_USER_AGENT or
                config.REDDIT_CLIENT_ID.strip() == "" or
                config.REDDIT_CLIENT_SECRET.strip() == "" or
                config.REDDIT_USER_AGENT.strip() == ""
            )
            
            # Debug logging (only if log_text exists)
            if hasattr(self, 'log_text'):
                self.log_message(f"🔍 Reddit Config Recheck:")
                self.log_message(f"  Client ID: '{config.REDDIT_CLIENT_ID}' (Default: {config.REDDIT_CLIENT_ID == default_client_id})")
                self.log_message(f"  Client Secret: '{config.REDDIT_CLIENT_SECRET}' (Default: {config.REDDIT_CLIENT_SECRET == default_client_secret})")
                self.log_message(f"  User Agent: '{config.REDDIT_USER_AGENT}' (Default: {config.REDDIT_USER_AGENT == default_user_agent})")
                self.log_message(f"  Is Default or Empty: {is_default_or_empty}")
            
            # Only change state if needed (avoid flicker)
            warning_currently_shown = hasattr(self, '_reddit_warning_shown') and self._reddit_warning_shown
            
            if is_default_or_empty and not warning_currently_shown:
                # Need to show warning and it's not currently shown
                self.show_reddit_config_warning()
                self._reddit_config_missing = True
                if hasattr(self, 'log_text'):
                    self.log_message("⚠️ Showing Reddit API warning - configuration needed")
            elif not is_default_or_empty and warning_currently_shown:
                # Don't need warning and it's currently shown
                self.hide_reddit_config_warning()
                self._reddit_config_missing = False
                if hasattr(self, 'log_text'):
                    self.log_message("✅ Reddit API configuration is properly set up")
            elif not is_default_or_empty:
                # Configuration is valid, just update the flag
                self._reddit_config_missing = False
                if hasattr(self, 'log_text'):
                    self.log_message("✅ Reddit API configuration confirmed valid")
                
        except Exception as e:
            # If config can't be imported or has issues, show warning
            if hasattr(self, 'log_text'):
                self.log_message(f"❌ Error checking Reddit config: {str(e)}")
            if not (hasattr(self, '_reddit_warning_shown') and self._reddit_warning_shown):
                self.show_reddit_config_warning()
            self._reddit_config_missing = True
    
    def clear_reddit_credentials(self):
        """Clear Reddit API credentials and reset to defaults"""
        try:
            # Confirm with user
            result = messagebox.askyesno(
                "Clear Reddit Credentials",
                "Are you sure you want to clear all Reddit API credentials?\n\n"
                "This will reset them to default placeholder values and\n"
                "the Reddit warning will appear again.\n\n"
                "You can reconfigure them anytime using 'Configure Reddit API'."
            )
            
            if not result:
                return
            
            # Read current config file
            config_path = os.path.join(os.path.dirname(__file__), "config.py")
            with open(config_path, 'r') as f:
                content = f.read()
            
            # Replace with placeholder values
            content = re.sub(r'REDDIT_CLIENT_ID\s*=\s*"[^"]*"', 
                           'REDDIT_CLIENT_ID     = "your_reddit_client_id_here"', content)
            content = re.sub(r'REDDIT_CLIENT_SECRET\s*=\s*"[^"]*"', 
                           'REDDIT_CLIENT_SECRET = "your_reddit_client_secret_here"', content)
            content = re.sub(r'REDDIT_USER_AGENT\s*=\s*"[^"]*"', 
                           'REDDIT_USER_AGENT    = "your-app-name/1.0 by u/yourusername"', content)
            
            # Write back to config file
            with open(config_path, 'w') as f:
                f.write(content)
            
            self.log_message("❌ Reddit API credentials cleared - reset to default placeholders")
            
            # Refresh the Reddit config check to show warning
            self.refresh_reddit_config_check()
            
            # Update status in settings dialog if it exists
            if hasattr(self, 'reddit_status_label'):
                self.update_reddit_status()
            
            messagebox.showinfo("Credentials Cleared", 
                              "✅ Reddit API credentials have been cleared!\n\n"
                              "All values have been reset to placeholder defaults.\n"
                              "Use 'Configure Reddit API' to set them up again.")
            
        except Exception as e:
            self.log_message(f"❌ Error clearing Reddit credentials: {str(e)}")
            messagebox.showerror("Error", f"Failed to clear credentials: {str(e)}")
    
    def clear_reddit_credentials_and_refresh(self, settings_dialog):
        """Clear Reddit credentials and refresh the settings dialog"""
        try:
            # Confirm with user first
            result = messagebox.askyesno(
                "Clear Reddit Credentials",
                "Are you sure you want to clear all Reddit API credentials?\n\n"
                "This will reset them to default placeholder values and\n"
                "the Reddit warning will appear again.\n\n"
                "You can reconfigure them anytime using 'Configure Reddit API'."
            )
            
            if not result:
                return
            
            # Read current config file
            config_path = os.path.join(os.path.dirname(__file__), "config.py")
            with open(config_path, 'r') as f:
                content = f.read()
            
            # Replace with placeholder values
            content = re.sub(r'REDDIT_CLIENT_ID\s*=\s*"[^"]*"', 
                           'REDDIT_CLIENT_ID     = "your_reddit_client_id_here"', content)
            content = re.sub(r'REDDIT_CLIENT_SECRET\s*=\s*"[^"]*"', 
                           'REDDIT_CLIENT_SECRET = "your_reddit_client_secret_here"', content)
            content = re.sub(r'REDDIT_USER_AGENT\s*=\s*"[^"]*"', 
                           'REDDIT_USER_AGENT    = "your-app-name/1.0 by u/yourusername"', content)
            
            # Write back to config file
            with open(config_path, 'w') as f:
                f.write(content)
            
            self.log_message("❌ Reddit API credentials cleared - reset to default placeholders")
            
            # Refresh the Reddit config check to show warning
            self.refresh_reddit_config_check()
            
            # Update status in current settings dialog if it still exists
            if hasattr(self, 'reddit_status_label') and self.reddit_status_label.winfo_exists():
                self.update_reddit_status()
            
            messagebox.showinfo("Credentials Cleared", 
                              "✅ Reddit API credentials have been cleared!\n\n"
                              "All values have been reset to placeholder defaults.\n"
                              "Use 'Configure Reddit API' to set them up again.")
            
        except Exception as e:
            self.log_message(f"❌ Error clearing credentials: {str(e)}")
            messagebox.showerror("Error", f"Failed to clear credentials: {str(e)}")
    
    def show_settings_dialog(self):
        """Show the settings configuration dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("⚙️ Settings")
        dialog.geometry("650x700")  # Made larger to ensure all content is visible
        dialog.configure(bg='#f8f9fa')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Create scrollable content
        canvas = tk.Canvas(dialog, bg='#f8f9fa', highlightthickness=0)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        main_frame = ttk.Frame(canvas)
        
        main_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=main_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pack the canvas and scrollbar
        canvas.pack(side="left", fill="both", expand=True, padx=(20, 0), pady=20)
        scrollbar.pack(side="right", fill="y", pady=20)
        
        # Bind mousewheel to canvas
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind("<MouseWheel>", _on_mousewheel)
        
        # Main content frame inside the scrollable area
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Title
        ttk.Label(content_frame, text="⚙️ Settings", 
                 font=('Segoe UI', 16, 'bold')).pack(pady=(0, 20))
        
        # YouTube API Settings Section
        yt_section = ttk.LabelFrame(content_frame, text="YouTube API Settings", padding=15)
        yt_section.pack(fill=tk.X, pady=(0, 15))
        
        # Current client_secrets.json path
        ttk.Label(yt_section, text="Client Secrets JSON File:", 
                 font=('Segoe UI', 10, 'bold')).pack(anchor=tk.W)
        
        path_frame = ttk.Frame(yt_section)
        path_frame.pack(fill=tk.X, pady=(5, 10))
        
        # Get current path
        import config
        current_path = config.YT_CLIENT_SECRETS
        if not os.path.isabs(current_path):
            current_path = os.path.join(os.path.dirname(__file__), current_path)
        
        self.client_secrets_var = tk.StringVar(value=current_path)
        path_entry = ttk.Entry(path_frame, textvariable=self.client_secrets_var, 
                              state='readonly', font=('Segoe UI', 9))
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Button(path_frame, text="📁 Browse", 
                  command=self.browse_client_secrets_file, style="TButton").pack(side=tk.RIGHT, padx=(5, 0))
        
        # Status indicator for client_secrets.json
        self.secrets_status_label = ttk.Label(yt_section, text="", font=('Segoe UI', 9))
        self.secrets_status_label.pack(anchor=tk.W, pady=(0, 5))
        self.update_secrets_status()
        
        # Reddit API Settings Section
        reddit_section = ttk.LabelFrame(content_frame, text="Reddit API Settings", padding=15)
        reddit_section.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(reddit_section, text="Quick access to Reddit API configuration:", 
                 font=('Segoe UI', 10)).pack(anchor=tk.W, pady=(0, 10))
        
        reddit_buttons_frame = ttk.Frame(reddit_section)
        reddit_buttons_frame.pack(fill=tk.X)
        
        ttk.Button(reddit_buttons_frame, text="⚙️ Configure Reddit API", 
                  command=lambda: [dialog.destroy(), self.show_reddit_config_dialog()], 
                  style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(reddit_buttons_frame, text="📖 Setup Guide", 
                  command=self.show_reddit_setup_guide, style="TButton").pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(reddit_buttons_frame, text="❌ Clear Credentials", 
                  command=lambda: self.clear_reddit_credentials_and_refresh(dialog), style="Danger.TButton").pack(side=tk.LEFT)
        
        # Status indicator for Reddit config
        self.reddit_status_label = ttk.Label(reddit_section, text="", font=('Segoe UI', 9))
        self.reddit_status_label.pack(anchor=tk.W, pady=(10, 0))
        self.update_reddit_status()
        
        # Application Settings Section
        app_section = ttk.LabelFrame(content_frame, text="Application Settings", padding=15)
        app_section.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Label(app_section, text="Additional application settings:", 
                 font=('Segoe UI', 10)).pack(anchor=tk.W, pady=(0, 10))
        
        app_buttons_frame = ttk.Frame(app_section)
        app_buttons_frame.pack(fill=tk.X)
        
        ttk.Button(app_buttons_frame, text="📁 Open Project Folder", 
                  command=self.open_project_folder, style="TButton").pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(app_buttons_frame, text="🔄 Reload All Data", 
                  command=self.reload_all_data, style="TButton").pack(side=tk.LEFT)
        
        # Token Management Section
        token_section = ttk.LabelFrame(content_frame, text="🔑 Token Management", padding=15)
        token_section.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(token_section, text="Clean up unused YouTube authentication tokens:", 
                 font=('Segoe UI', 10)).pack(anchor=tk.W, pady=(0, 10))
        
        token_buttons_frame = ttk.Frame(token_section)
        token_buttons_frame.pack(fill=tk.X)
        
        # Both buttons side by side
        
        ttk.Button(token_buttons_frame, text="  Open Tokens Folder", 
                  command=lambda: os.startfile(os.path.join(os.path.dirname(__file__), "tokens")), 
                  style="TButton").pack(side=tk.LEFT, padx=(0, 10))
        
        cleanup_btn = ttk.Button(token_buttons_frame, text="🗑️ Delete Unused Tokens", 
                                command=self.quick_cleanup_tokens, 
                                style="Danger.TButton")
        cleanup_btn.pack(side=tk.LEFT)
        

        
        # Bottom buttons
        button_frame = ttk.Frame(content_frame)
        button_frame.pack(fill=tk.X, pady=(20, 0))
        
        ttk.Button(button_frame, text="💾 Save & Close", 
                  command=lambda: self.save_settings_and_close(dialog), 
                  style="Accent.TButton").pack(side=tk.RIGHT, padx=(5, 0))
        
        ttk.Button(button_frame, text="❌ Cancel", 
                  command=dialog.destroy, style="Danger.TButton").pack(side=tk.RIGHT)
    
    def browse_client_secrets_file(self):
        """Browse for a new client_secrets.json file"""
        filename = filedialog.askopenfilename(
            title="Select client_secrets.json file",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=os.path.dirname(self.client_secrets_var.get())
        )
        if filename:
            self.client_secrets_var.set(filename)
            self.update_secrets_status()
    
    def update_secrets_status(self):
        """Update the status of the client_secrets.json file"""
        path = self.client_secrets_var.get()
        if os.path.exists(path):
            self.secrets_status_label.config(
                text="✅ File exists and accessible", 
                foreground='green'
            )
        else:
            self.secrets_status_label.config(
                text="❌ File not found or inaccessible", 
                foreground='red'
            )
    
    def update_reddit_status(self):
        """Update the status of Reddit API configuration"""
        try:
            # Check if the reddit_status_label widget still exists
            if not hasattr(self, 'reddit_status_label') or not self.reddit_status_label.winfo_exists():
                return
            
            # Force clear any cached config module
            import sys
            if 'config' in sys.modules:
                del sys.modules['config']
            
            import config
            
            default_values = [
                'your_reddit_client_id_here', 
                'your_reddit_client_secret_here', 
                'your-app-name/1.0 by u/yourusername', 
                'Enter your Reddit app Client ID', 
                'Enter your Reddit app Client Secret', 
                'youtube-shorts-bot/1.0 by u/yourusername'
            ]
            
            has_defaults_or_empty = (
                any(val in default_values for val in [
                    config.REDDIT_CLIENT_ID, 
                    config.REDDIT_CLIENT_SECRET, 
                    config.REDDIT_USER_AGENT
                ]) or
                not config.REDDIT_CLIENT_ID or 
                not config.REDDIT_CLIENT_SECRET or 
                not config.REDDIT_USER_AGENT or
                config.REDDIT_CLIENT_ID.strip() == "" or
                config.REDDIT_CLIENT_SECRET.strip() == "" or
                config.REDDIT_USER_AGENT.strip() == ""
            )
            
            if has_defaults_or_empty:
                self.reddit_status_label.config(
                    text="❌ Configuration required", 
                    foreground='red'
                )
            else:
                self.reddit_status_label.config(
                    text="✅ Reddit API configured", 
                    foreground='green'
                )
        except tk.TclError:
            # Widget was destroyed, ignore
            pass
        except Exception as e:
            # Only try to update label if it still exists
            try:
                if hasattr(self, 'reddit_status_label') and self.reddit_status_label.winfo_exists():
                    self.reddit_status_label.config(
                        text=f"❌ Error checking configuration: {str(e)}", 
                        foreground='red'
                    )
            except tk.TclError:
                # Widget was destroyed, ignore
                pass
    
    def open_project_folder(self):
        """Open the project folder in file explorer"""
        try:
            project_path = os.path.dirname(__file__)
            os.startfile(project_path)  # Windows
            self.log_message(f"📁 Opened project folder: {project_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open project folder: {str(e)}")
    
    def reload_all_data(self):
        """Reload all application data"""
        try:
            # Reload profiles
            self.load_profiles()
            self.refresh_profile_list()
            
            # Refresh channel status
            if hasattr(self, 'refresh_channel_status'):
                self.refresh_channel_status()
            
            # Update system info
            if hasattr(self, 'update_system_info'):
                self.update_system_info()
            
            # Refresh startup display
            if hasattr(self, 'refresh_startup_display'):
                self.refresh_startup_display()
            
            # Recheck API configurations
            self.check_client_secrets_exists()
            self.check_reddit_config()
            self.check_storage_space()
            
            self.log_message("🔄 All application data reloaded successfully")
            messagebox.showinfo("Reload Complete", "All application data has been reloaded successfully!")
            
        except Exception as e:
            error_msg = f"Failed to reload data: {str(e)}"
            self.log_message(f"❌ {error_msg}")
            messagebox.showerror("Reload Error", error_msg)
    
    def save_settings_and_close(self, dialog):
        """Save settings and close the dialog"""
        try:
            # Update the client_secrets path in config.py
            new_path = self.client_secrets_var.get()
            
            # Convert to relative path if it's in the same directory
            project_dir = os.path.dirname(__file__)
            if os.path.dirname(new_path) == project_dir:
                new_path = os.path.basename(new_path)
            
            # Read current config file
            config_path = os.path.join(project_dir, "config.py")
            with open(config_path, 'r') as f:
                content = f.read()
            
            # Replace the YT_CLIENT_SECRETS value
            import re
            content = re.sub(
                r'YT_CLIENT_SECRETS\s*=\s*"[^"]*"', 
                f'YT_CLIENT_SECRETS    = "{new_path}"', 
                content
            )
            
            # Write back to config file
            with open(config_path, 'w') as f:
                f.write(content)
            
            self.log_message("✅ Settings saved successfully")
            
            # Refresh configurations
            self.check_client_secrets_exists()
            self.check_reddit_config()
            
            dialog.destroy()
            
        except Exception as e:
            error_msg = f"Failed to save settings: {str(e)}"
            messagebox.showerror("Save Error", error_msg)
            self.log_message(f"❌ {error_msg}")
    
    def setup_gui(self):
        """Setup the main GUI layout"""
        # Configure root window for proper resizing
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Create main frame with padding
        main_frame = ttk.Frame(self.root)
        main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(5, weight=1)  # Changed from 2 to 5 to accommodate warning frames
        
        # Modern title with status
        title_frame = ttk.Frame(main_frame)
        title_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        title_frame.columnconfigure(0, weight=1)
        
        title_label = ttk.Label(title_frame, text="🎬 YouTube Shorts Bot Manager", 
                               font=('Segoe UI', 24, 'bold'))
        title_label.grid(row=0, column=0, sticky="w")
        
        # Status indicator
        self.main_status = ttk.Label(title_frame, text="● Ready", 
                                    font=('Segoe UI', 12), foreground='#00aa00')
        self.main_status.grid(row=0, column=1, sticky="e")
        
        # Tabs header with settings button
        tabs_header = ttk.Frame(main_frame)
        tabs_header.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        tabs_header.columnconfigure(0, weight=1)
        
        # Settings button aligned with tab level
        ttk.Button(tabs_header, text="⚙️ Settings", 
                  command=self.show_settings_dialog,
                  style="TButton").grid(row=0, column=1, sticky="e")
        
        # Main notebook
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=5, column=0, sticky="nsew")  # Changed from row=2 to row=5
        
        # Bind tab change event to check for unsaved changes
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)
        self.current_tab_index = 0  # Track current tab
        
        # Create and set up all tab frames immediately
        self.profile_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.profile_frame, text="📋 Channel Profiles")
        
        self.processing_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.processing_frame, text="⚡ Process Channels")
        
        self.startup_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.startup_frame, text="🌅 Startup Management")
        
        self.logs_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.logs_frame, text="📜 Logs & Status")
        
        # Set up all tabs immediately
        self.setup_profile_tab()
        self.setup_processing_tab()
        self.setup_startup_tab()
        self.setup_logs_tab()
        
        # Refresh displays after all tabs are set up
        self.refresh_profile_list()
        self.refresh_channel_status()
        
        # Warning banner frames (initially hidden)
        self.warning_frame = ttk.Frame(main_frame)
        self.reddit_warning_frame = ttk.Frame(main_frame)
        self.storage_warning_frame = ttk.Frame(main_frame)
        self.root.after_idle(self.check_storage_space)
    
    def setup_profile_tab(self):
        """Setup the profile management tab"""
        # Configure tab for responsive layout
        self.profile_frame.columnconfigure(0, weight=1)
        self.profile_frame.rowconfigure(0, weight=1)
        
        # Create paned window for resizable layout
        paned = ttk.PanedWindow(self.profile_frame, orient=tk.HORIZONTAL)
        paned.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # Left panel - Profile list
        left_panel = ttk.Frame(paned)
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(1, weight=1)
        paned.add(left_panel, weight=1)
        
        # Profile list header
        list_header = ttk.Frame(left_panel)
        list_header.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        list_header.columnconfigure(0, weight=1)
        
        ttk.Label(list_header, text="Channel Profiles", 
                 font=('Segoe UI', 14, 'bold')).grid(row=0, column=0, sticky="w")
        
        ttk.Button(list_header, text="➕ New", command=self.new_profile,
                  style="Accent.TButton").grid(row=0, column=2, padx=(5, 0))
        ttk.Button(list_header, text="❌ Delete", command=self.delete_profile, 
                  style="Danger.TButton").grid(row=0, column=1, padx=(5, 0))
        
        # Profile listbox with modern styling
        list_frame = ttk.Frame(left_panel)
        list_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 15))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        self.profile_listbox = tk.Listbox(list_frame, font=('Segoe UI', 11),
                                         bg='white', fg='black', selectbackground='#0078d4',
                                         selectforeground='white', borderwidth=1, relief='solid')
        list_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.profile_listbox.yview)
        self.profile_listbox.configure(yscrollcommand=list_scrollbar.set)
        
        self.profile_listbox.grid(row=0, column=0, sticky="nsew")
        list_scrollbar.grid(row=0, column=1, sticky="ns")
        self.profile_listbox.bind('<<ListboxSelect>>', self.on_profile_select)
        
        # Action buttons
        action_frame = ttk.Frame(left_panel)
        action_frame.grid(row=2, column=0, sticky="ew")
        action_frame.columnconfigure(0, weight=1)
        
        ttk.Button(action_frame, text="💾 Save Changes", command=self.save_profiles,
                  style="Accent.TButton").grid(row=0, column=0, sticky="ew", pady=2)
        ttk.Button(action_frame, text="🔄 Reload", command=self.reload_profiles, 
                  style="TButton").grid(row=1, column=0, sticky="ew", pady=2)
        
        # Right panel - Profile editor
        right_panel = ttk.Frame(paned)
        paned.add(right_panel, weight=2)
        
        # Editor header
        editor_header = ttk.Frame(right_panel)
        editor_header.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Label(editor_header, text="Profile Editor", 
                 font=('Segoe UI', 14, 'bold')).pack(side=tk.LEFT)
        
        self.save_indicator = ttk.Label(editor_header, text="", foreground='#00aa00')
        self.save_indicator.pack(side=tk.RIGHT)
        
        # Scrollable editor area
        canvas = tk.Canvas(right_panel, bg='#f8f9fa', highlightthickness=0)
        scrollbar = ttk.Scrollbar(right_panel, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bind mousewheel to canvas
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind("<MouseWheel>", _on_mousewheel)
        
        self.setup_profile_editor()
        self.refresh_profile_list()
    
    def setup_profile_editor(self):
        """Setup the modern profile editor fields"""
        self.profile_vars = {}
        
        # Create placeholder message for when no profile is selected
        self.setup_placeholder_message()
        
        # Create the actual editor fields (initially hidden)
        self.setup_actual_editor()
        
        # Show placeholder by default
        self.show_placeholder()
    
    def setup_placeholder_message(self):
        """Setup the placeholder message shown when no profile is selected"""
        self.placeholder_frame = ttk.Frame(self.scrollable_frame, style='Placeholder.TFrame')
        
        # Add some padding to center the content, with more left padding to shift right
        padding_frame = ttk.Frame(self.placeholder_frame)
        padding_frame.pack(expand=True, fill='both', padx=(180, 50), pady=160)
        
        # Center the content horizontally, but shifted more to the right
        center_frame = ttk.Frame(padding_frame)
        center_frame.pack(anchor='center')
        
        # Icon and message - now properly centered and shifted right
        ttk.Label(center_frame, text="📋", font=('Segoe UI', 48)).pack(pady=(0, 20))
        
        ttk.Label(center_frame, text="Select a channel profile to get started", 
                 font=('Segoe UI', 16, 'bold'), foreground='#666666').pack(pady=(0, 10))
        
        ttk.Label(center_frame, text="Choose a profile from the list on the left to view and edit its settings,\nor create a new profile to begin setting up your first channel.", 
                 font=('Segoe UI', 11), foreground='#888888', justify='center').pack(pady=(0, 0))
        
        # Configure a simple style for debugging
        style = ttk.Style()
        style.configure('Placeholder.TFrame', background='#f8f9fa')
    
    def setup_actual_editor(self):
        """Setup the actual profile editor fields (initially hidden)"""
        self.editor_frame = ttk.Frame(self.scrollable_frame)
    def setup_actual_editor(self):
        """Setup the actual profile editor fields (initially hidden)"""
        self.editor_frame = ttk.Frame(self.scrollable_frame)
        
        # Helper function to add text selection protection to Entry widgets
        def add_text_selection_protection(entry_widget):
            """Add event bindings to protect against profile switching during text selection"""
            # Protection mechanism temporarily disabled to fix listbox interaction issues
            pass
        
        # Basic settings with modern card-like appearance
        basic_frame = ttk.LabelFrame(self.editor_frame, text="🔧 Basic Settings", padding=20)
        basic_frame.pack(fill=tk.X, pady=(0, 20), padx=10)
        
        # Grid configuration
        basic_frame.columnconfigure(1, weight=1)
        
        # Channel Label
        ttk.Label(basic_frame, text="Channel Label:", font=('Segoe UI', 10, 'bold')).grid(
            row=0, column=0, sticky=tk.W, padx=(0, 15), pady=8)
        self.profile_vars['label'] = tk.StringVar()
        label_entry = ttk.Entry(basic_frame, textvariable=self.profile_vars['label'], font=('Segoe UI', 10))
        label_entry.grid(row=0, column=1, sticky=tk.EW, pady=8)
        add_text_selection_protection(label_entry)
        
        # Subreddit
        ttk.Label(basic_frame, text="Subreddit:", font=('Segoe UI', 10, 'bold')).grid(
            row=1, column=0, sticky=tk.W, padx=(0, 15), pady=8)
        subreddit_frame = ttk.Frame(basic_frame)
        subreddit_frame.grid(row=1, column=1, sticky=tk.EW, pady=8)
        ttk.Label(subreddit_frame, text="r/", font=('Segoe UI', 10)).pack(side=tk.LEFT)
        self.profile_vars['subreddit'] = tk.StringVar()
        subreddit_entry = ttk.Entry(subreddit_frame, textvariable=self.profile_vars['subreddit'], font=('Segoe UI', 10))
        subreddit_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        add_text_selection_protection(subreddit_entry)
        
        # YouTube Token with browse button
        ttk.Label(basic_frame, text="YouTube Token:", font=('Segoe UI', 10, 'bold')).grid(
            row=2, column=0, sticky=tk.W, padx=(0, 15), pady=8)
        token_frame = ttk.Frame(basic_frame)
        token_frame.grid(row=2, column=1, sticky=tk.EW, pady=8)
        token_frame.columnconfigure(0, weight=1)
        self.profile_vars['yt_token'] = tk.StringVar()
        yt_token_entry = ttk.Entry(token_frame, textvariable=self.profile_vars['yt_token'], font=('Segoe UI', 10))
        yt_token_entry.grid(row=0, column=0, sticky=tk.EW, padx=(0, 10))
        add_text_selection_protection(yt_token_entry)
        ttk.Button(token_frame, text="📁 Browse", command=self.browse_token_file, 
                  style="TButton").grid(row=0, column=1)
        
        # Horizontal Zoom with spinbox instead of slider
        ttk.Label(basic_frame, text="Horizontal Zoom:", font=('Segoe UI', 10, 'bold')).grid(
            row=3, column=0, sticky=tk.W, padx=(0, 15), pady=8)
        zoom_frame = ttk.Frame(basic_frame)
        zoom_frame.grid(row=3, column=1, sticky=tk.W, pady=8)
        self.profile_vars['horizontal_zoom'] = tk.DoubleVar(value=1.6)
        
        # Use safe Entry + button approach instead of problematic Spinbox
        zoom_frame_inner = ttk.Frame(zoom_frame)
        zoom_frame_inner.pack(side=tk.LEFT)
        
        # Entry field for manual input
        zoom_entry = ttk.Entry(zoom_frame_inner, textvariable=self.profile_vars['horizontal_zoom'], 
                              width=8, font=('Segoe UI', 10), justify='center')
        zoom_entry.pack(side=tk.LEFT)
        add_text_selection_protection(zoom_entry)
        
        # Small up/down buttons that look like spinbox arrows
        zoom_buttons = ttk.Frame(zoom_frame_inner)
        zoom_buttons.pack(side=tk.LEFT, padx=(2, 0))
        
        def increment_zoom():
            try:
                current = float(self.profile_vars['horizontal_zoom'].get())
                new_val = min(3.0, current + 0.1)
                self.profile_vars['horizontal_zoom'].set(round(new_val, 1))
            except (ValueError, tk.TclError):
                self.profile_vars['horizontal_zoom'].set(1.6)
        
        def decrement_zoom():
            try:
                current = float(self.profile_vars['horizontal_zoom'].get())
                new_val = max(1.0, current - 0.1)
                self.profile_vars['horizontal_zoom'].set(round(new_val, 1))
            except (ValueError, tk.TclError):
                self.profile_vars['horizontal_zoom'].set(1.6)
        
        # Create small arrow buttons using tk.Button for better size control
        up_btn = tk.Button(zoom_buttons, text="▲", font=('Segoe UI', 6), 
                          width=2, height=1, pady=0, command=increment_zoom,
                          bg='#f0f0f0', relief='raised', bd=1)
        up_btn.pack(side=tk.TOP, pady=(0, 1))
        down_btn = tk.Button(zoom_buttons, text="▼", font=('Segoe UI', 6),
                            width=2, height=1, pady=0, command=decrement_zoom,
                            bg='#f0f0f0', relief='raised', bd=1)
        down_btn.pack(side=tk.TOP)
        ttk.Label(zoom_frame, text="(1.0 = no zoom, 2.0 = 2x zoom)", 
                 font=('Segoe UI', 9), foreground='gray').pack(side=tk.LEFT, padx=(10, 0))
        
        # Run on Startup checkbox
        ttk.Label(basic_frame, text="Run on Startup:", font=('Segoe UI', 10, 'bold')).grid(
            row=4, column=0, sticky=tk.W, padx=(0, 15), pady=8)
        startup_frame = ttk.Frame(basic_frame)
        startup_frame.grid(row=4, column=1, sticky=tk.W, pady=8)
        self.profile_vars['run_on_startup'] = tk.BooleanVar(value=False)
        startup_check = ttk.Checkbutton(startup_frame, text="Enable this channel to run automatically when computer starts",
                                       variable=self.profile_vars['run_on_startup'], style="Startup.TCheckbutton")
        startup_check.pack(side=tk.LEFT)
        
        # Daily Upload Limit
        ttk.Label(basic_frame, text="Daily Upload Limit:", font=('Segoe UI', 10, 'bold')).grid(
            row=5, column=0, sticky=tk.W, padx=(0, 15), pady=8)
        upload_limit_frame = ttk.Frame(basic_frame)
        upload_limit_frame.grid(row=5, column=1, sticky=tk.W, pady=8)
        self.profile_vars['daily_upload_limit'] = tk.IntVar(value=1)
        
        # Use safe Entry + button approach instead of problematic Spinbox
        upload_frame_inner = ttk.Frame(upload_limit_frame)
        upload_frame_inner.pack(side=tk.LEFT)
        
        # Entry field for manual input
        upload_entry = ttk.Entry(upload_frame_inner, textvariable=self.profile_vars['daily_upload_limit'], 
                                width=8, font=('Segoe UI', 10), justify='center')
        upload_entry.pack(side=tk.LEFT)
        add_text_selection_protection(upload_entry)
        
        # Small up/down buttons that look like spinbox arrows
        upload_buttons = ttk.Frame(upload_frame_inner)
        upload_buttons.pack(side=tk.LEFT, padx=(2, 0))
        
        def increment_upload():
            try:
                current = int(self.profile_vars['daily_upload_limit'].get())
                new_val = min(15, current + 1)
                self.profile_vars['daily_upload_limit'].set(new_val)
            except (ValueError, tk.TclError):
                self.profile_vars['daily_upload_limit'].set(1)
        
        def decrement_upload():
            try:
                current = int(self.profile_vars['daily_upload_limit'].get())
                new_val = max(1, current - 1)
                self.profile_vars['daily_upload_limit'].set(new_val)
            except (ValueError, tk.TclError):
                self.profile_vars['daily_upload_limit'].set(1)
        
        # Create small arrow buttons using tk.Button for better size control
        up_btn = tk.Button(upload_buttons, text="▲", font=('Segoe UI', 6), 
                          width=2, height=1, pady=0, command=increment_upload,
                          bg='#f0f0f0', relief='raised', bd=1)
        up_btn.pack(side=tk.TOP, pady=(0, 1))
        down_btn = tk.Button(upload_buttons, text="▼", font=('Segoe UI', 6),
                            width=2, height=1, pady=0, command=decrement_upload,
                            bg='#f0f0f0', relief='raised', bd=1)
        down_btn.pack(side=tk.TOP)
        ttk.Label(upload_limit_frame, text="videos per day (YouTube's standard limit is 15)", 
                 font=('Segoe UI', 9), foreground='gray').pack(side=tk.LEFT, padx=(10, 0))
        
        # Video Selection Settings
        video_selection_frame = ttk.LabelFrame(self.editor_frame, text="🎯 Video Selection Settings", padding=20)
        video_selection_frame.pack(fill=tk.X, pady=(0, 20), padx=10)
        video_selection_frame.columnconfigure(1, weight=1)
        
        # Primary Sort Method
        ttk.Label(video_selection_frame, text="Primary Sort Method:", font=('Segoe UI', 10, 'bold')).grid(
            row=0, column=0, sticky=tk.W, padx=(0, 15), pady=8)
        sort_frame = ttk.Frame(video_selection_frame)
        sort_frame.grid(row=0, column=1, sticky=tk.W, pady=8)
        
        self.profile_vars['video_sort_method'] = tk.StringVar(value="top_month")
        sort_options = [
            ("🔥 Hot (Reddit's trending algorithm)", "hot"),
            ("⭐ Top - All Time", "top_all"),
            ("🏆 Top - This Year", "top_year"), 
            ("📆 Top - This Month", "top_month"),
            ("📰 Newest", "new")
        ]
        
        # Create radio buttons in a clean layout
        for i, (display_text, value) in enumerate(sort_options):
            radio_btn = ttk.Radiobutton(sort_frame, text=display_text, 
                                      variable=self.profile_vars['video_sort_method'], 
                                      value=value, style="TRadiobutton")
            radio_btn.grid(row=i, column=0, sticky=tk.W, pady=3, padx=(0, 10))
        
        # Fallback behavior
        ttk.Label(video_selection_frame, text="Fallback Behavior:", font=('Segoe UI', 10, 'bold')).grid(
            row=1, column=0, sticky=tk.W, padx=(0, 15), pady=(15, 8))
        fallback_frame = ttk.Frame(video_selection_frame)
        fallback_frame.grid(row=1, column=1, sticky=tk.W, pady=(15, 8))
        
        self.profile_vars['enable_fallback'] = tk.BooleanVar(value=True)
        fallback_check = ttk.Checkbutton(fallback_frame, text="Enable automatic fallback to broader time periods",
                                        variable=self.profile_vars['enable_fallback'], style="TCheckbutton")
        fallback_check.pack(anchor=tk.W)
        
        # Fallback explanation
        ttk.Label(fallback_frame, text="When enabled: Month → Year → All Time → Hot → Newest", 
                 font=('Segoe UI', 9), foreground='gray').pack(anchor=tk.W, pady=(5, 0))
        ttk.Label(fallback_frame, text="If no suitable video is found, the system will try broader time periods automatically.", 
                 font=('Segoe UI', 9), foreground='gray').pack(anchor=tk.W)
        
        # Hashtags section with add/remove/edit functionality
        hashtag_frame = ttk.LabelFrame(self.editor_frame, text="🏷️ Hashtags", padding=20)
        hashtag_frame.pack(fill=tk.X, pady=(0, 20), padx=10)
        
        hashtag_top = ttk.Frame(hashtag_frame)
        hashtag_top.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(hashtag_top, text="Manage hashtags for your videos:", font=('Segoe UI', 10)).pack(side=tk.LEFT)
        
        hashtag_buttons = ttk.Frame(hashtag_top)
        hashtag_buttons.pack(side=tk.RIGHT)
        ttk.Button(hashtag_buttons, text="➕ Add", command=self.add_hashtag, 
                  style="Accent.TButton").pack(side=tk.LEFT, padx=2)
        ttk.Button(hashtag_buttons, text="✏️ Edit", command=self.edit_hashtag, 
                  style="TButton").pack(side=tk.LEFT, padx=2)
        ttk.Button(hashtag_buttons, text="❌ Remove", command=self.remove_hashtag, 
                  style="Danger.TButton").pack(side=tk.LEFT, padx=2)
        
        # Hashtags listbox
        hashtag_list_frame = ttk.Frame(hashtag_frame)
        hashtag_list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.hashtags_listbox = tk.Listbox(hashtag_list_frame, height=6, font=('Segoe UI', 10),
                                          bg='white', fg='black', selectbackground='#0078d4')
        hashtag_scroll = ttk.Scrollbar(hashtag_list_frame, orient=tk.VERTICAL, command=self.hashtags_listbox.yview)
        self.hashtags_listbox.configure(yscrollcommand=hashtag_scroll.set)
        
        self.hashtags_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        hashtag_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Sample Titles section with add/remove/edit functionality
        titles_frame = ttk.LabelFrame(self.editor_frame, text="💬 Sample Titles", padding=20)
        titles_frame.pack(fill=tk.X, pady=(0, 20), padx=10)
        
        titles_top = ttk.Frame(titles_frame)
        titles_top.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(titles_top, text="Sample titles for video text overlay:", font=('Segoe UI', 10)).pack(side=tk.LEFT)
        
        titles_buttons = ttk.Frame(titles_top)
        titles_buttons.pack(side=tk.RIGHT)
        ttk.Button(titles_buttons, text="➕ Add", command=self.add_title, 
                  style="Accent.TButton").pack(side=tk.LEFT, padx=2)
        ttk.Button(titles_buttons, text="✏️ Edit", command=self.edit_title, 
                  style="TButton").pack(side=tk.LEFT, padx=2)
        ttk.Button(titles_buttons, text="❌ Remove", command=self.remove_title, 
                  style="Danger.TButton").pack(side=tk.LEFT, padx=2)
        
        # Titles listbox
        titles_list_frame = ttk.Frame(titles_frame)
        titles_list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.titles_listbox = tk.Listbox(titles_list_frame, height=8, font=('Segoe UI', 10),
                                        bg='white', fg='black', selectbackground='#0078d4')
        titles_scroll = ttk.Scrollbar(titles_list_frame, orient=tk.VERTICAL, command=self.titles_listbox.yview)
        self.titles_listbox.configure(yscrollcommand=titles_scroll.set)
        
        self.titles_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        titles_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Font Settings
        font_frame = ttk.LabelFrame(self.editor_frame, text="🔤 Font Settings", padding=20)
        font_frame.pack(fill=tk.X, pady=(0, 20), padx=10)
        font_frame.columnconfigure(1, weight=1)
        
        # Font Path
        ttk.Label(font_frame, text="Font File:", font=('Segoe UI', 10, 'bold')).grid(
            row=0, column=0, sticky=tk.W, padx=(0, 15), pady=8)
        font_path_frame = ttk.Frame(font_frame)
        font_path_frame.grid(row=0, column=1, sticky=tk.EW, pady=8)
        font_path_frame.columnconfigure(0, weight=1)
        self.profile_vars['font_path'] = tk.StringVar(value="C:\\Windows\\Fonts\\impact.ttf")
        font_path_entry = ttk.Entry(font_path_frame, textvariable=self.profile_vars['font_path'], font=('Segoe UI', 10))
        font_path_entry.grid(row=0, column=0, sticky=tk.EW, padx=(0, 10))
        add_text_selection_protection(font_path_entry)
        ttk.Button(font_path_frame, text="📁 Browse", command=self.browse_font_file, 
                  style="TButton").grid(row=0, column=1)
        
        # Font Size
        ttk.Label(font_frame, text="Font Size:", font=('Segoe UI', 10, 'bold')).grid(
            row=1, column=0, sticky=tk.W, padx=(0, 15), pady=8)
        font_size_frame = ttk.Frame(font_frame)
        font_size_frame.grid(row=1, column=1, sticky=tk.W, pady=8)
        self.profile_vars['font_size'] = tk.IntVar(value=70)
        
        # Use safe Entry + button approach instead of problematic Spinbox
        font_frame_inner = ttk.Frame(font_size_frame)
        font_frame_inner.pack(side=tk.LEFT)
        
        # Entry field for manual input
        font_entry = ttk.Entry(font_frame_inner, textvariable=self.profile_vars['font_size'], 
                              width=8, font=('Segoe UI', 10), justify='center')
        font_entry.pack(side=tk.LEFT)
        add_text_selection_protection(font_entry)
        
        # Small up/down buttons that look like spinbox arrows
        font_buttons = ttk.Frame(font_frame_inner)
        font_buttons.pack(side=tk.LEFT, padx=(2, 0))
        
        def increment_font():
            try:
                current = int(self.profile_vars['font_size'].get())
                new_val = min(200, current + 1)
                self.profile_vars['font_size'].set(new_val)
            except (ValueError, tk.TclError):
                self.profile_vars['font_size'].set(70)
        
        def decrement_font():
            try:
                current = int(self.profile_vars['font_size'].get())
                new_val = max(20, current - 1)
                self.profile_vars['font_size'].set(new_val)
            except (ValueError, tk.TclError):
                self.profile_vars['font_size'].set(70)
        
        # Create small arrow buttons using tk.Button for better size control
        up_btn = tk.Button(font_buttons, text="▲", font=('Segoe UI', 6), 
                          width=2, height=1, pady=0, command=increment_font,
                          bg='#f0f0f0', relief='raised', bd=1)
        up_btn.pack(side=tk.TOP, pady=(0, 1))
        down_btn = tk.Button(font_buttons, text="▼", font=('Segoe UI', 6),
                            width=2, height=1, pady=0, command=decrement_font,
                            bg='#f0f0f0', relief='raised', bd=1)
        down_btn.pack(side=tk.TOP)
        ttk.Label(font_size_frame, text="pixels", font=('Segoe UI', 9), foreground='gray').pack(side=tk.LEFT, padx=(10, 0))
        
        # Text Position (Y coordinate)
        ttk.Label(font_frame, text="Text Position:", font=('Segoe UI', 10, 'bold')).grid(
            row=2, column=0, sticky=tk.W, padx=(0, 15), pady=8)
        text_position_frame = ttk.Frame(font_frame)
        text_position_frame.grid(row=2, column=1, sticky=tk.W, pady=8)
        self.profile_vars['text_position_y'] = tk.IntVar(value=320)
        
        # Use safe Entry + button approach instead of problematic Spinbox
        position_frame_inner = ttk.Frame(text_position_frame)
        position_frame_inner.pack(side=tk.LEFT)
        
        # Entry field for manual input
        position_entry = ttk.Entry(position_frame_inner, textvariable=self.profile_vars['text_position_y'], 
                                  width=8, font=('Segoe UI', 10), justify='center')
        position_entry.pack(side=tk.LEFT)
        add_text_selection_protection(position_entry)
        
        # Small up/down buttons that look like spinbox arrows
        position_buttons = ttk.Frame(position_frame_inner)
        position_buttons.pack(side=tk.LEFT, padx=(2, 0))
        
        def increment_position():
            try:
                current = int(self.profile_vars['text_position_y'].get())
                new_val = min(800, current + 10)
                self.profile_vars['text_position_y'].set(new_val)
            except (ValueError, tk.TclError):
                self.profile_vars['text_position_y'].set(320)
        
        def decrement_position():
            try:
                current = int(self.profile_vars['text_position_y'].get())
                new_val = max(50, current - 10)
                self.profile_vars['text_position_y'].set(new_val)
            except (ValueError, tk.TclError):
                self.profile_vars['text_position_y'].set(320)
        
        # Create small arrow buttons using tk.Button for better size control
        up_btn = tk.Button(position_buttons, text="▲", font=('Segoe UI', 6), 
                          width=2, height=1, pady=0, command=increment_position,
                          bg='#f0f0f0', relief='raised', bd=1)
        up_btn.pack(side=tk.TOP, pady=(0, 1))
        down_btn = tk.Button(position_buttons, text="▼", font=('Segoe UI', 6),
                            width=2, height=1, pady=0, command=decrement_position,
                            bg='#f0f0f0', relief='raised', bd=1)
        down_btn.pack(side=tk.TOP)
        ttk.Label(text_position_frame, text="pixels from top (higher = lower on screen)", 
                 font=('Segoe UI', 9), foreground='gray').pack(side=tk.LEFT, padx=(10, 0))
        
        # Music Settings (NEW SECTION)
        music_settings_frame = ttk.LabelFrame(self.editor_frame, text="🎵 Music Settings", padding=20)
        music_settings_frame.pack(fill=tk.X, pady=(0, 20), padx=10)
        music_settings_frame.columnconfigure(1, weight=1)
        
        # Music Mode Selection
        ttk.Label(music_settings_frame, text="Music Mode:", font=('Segoe UI', 10, 'bold')).grid(
            row=2, column=0, sticky=tk.W, padx=(0, 15), pady=8)
        music_mode_frame = ttk.Frame(music_settings_frame)
        music_mode_frame.grid(row=2, column=1, sticky=tk.W, pady=8)
        
        self.profile_vars['music_mode'] = tk.StringVar(value="smart")
        
        # Music Directory with browse button
        ttk.Label(music_settings_frame, text="Music Directory:", font=('Segoe UI', 10, 'bold')).grid(
            row=1, column=0, sticky=tk.W, padx=(0, 15), pady=8)
        music_frame = ttk.Frame(music_settings_frame)
        music_frame.grid(row=1, column=1, sticky=tk.EW, pady=8)
        music_frame.columnconfigure(0, weight=1)
        self.profile_vars['music_dir'] = tk.StringVar()
        music_dir_entry = ttk.Entry(music_frame, textvariable=self.profile_vars['music_dir'], font=('Segoe UI', 10))
        music_dir_entry.grid(row=0, column=0, sticky=tk.EW, padx=(0, 10))
        add_text_selection_protection(music_dir_entry)
        ttk.Button(music_frame, text="📁 Browse", command=self.browse_music_dir, 
                  style="TButton").grid(row=0, column=1)
        
        # Create radio buttons for music modes
        music_options = [
            ("🚫 No Music", "disabled", "Never add background music to videos"),
            ("🎵 Always Add Music", "always", "Always add background music to all videos"),
            ("🧠 Smart Mode", "smart", "Automatically detect silent videos and add music only when needed")
        ]
        
        for i, (display_text, value, description) in enumerate(music_options):
            radio_btn = ttk.Radiobutton(music_mode_frame, text=display_text, 
                                      variable=self.profile_vars['music_mode'], 
                                      value=value, style="TRadiobutton")
            radio_btn.grid(row=i, column=0, sticky=tk.W, pady=3)
            
            # Add description text
            desc_label = ttk.Label(music_mode_frame, text=description, 
                                 font=('Segoe UI', 9), foreground='gray')
            desc_label.grid(row=i, column=1, sticky=tk.W, padx=(10, 0), pady=3)
        
        # Music Volume Control
        ttk.Label(music_settings_frame, text="Music Volume:", font=('Segoe UI', 10, 'bold')).grid(
            row=3, column=0, sticky=tk.W, padx=(0, 15), pady=8)
        volume_frame = ttk.Frame(music_settings_frame)
        volume_frame.grid(row=3, column=1, sticky=tk.EW, pady=8)
        volume_frame.columnconfigure(1, weight=1)
        
        self.profile_vars['music_volume'] = tk.DoubleVar(value=0.3)  # Default to 30% volume
        
        # Volume scale
        volume_scale = ttk.Scale(volume_frame, from_=0.0, to=1.0, orient='horizontal',
                               variable=self.profile_vars['music_volume'], length=200)
        volume_scale.grid(row=0, column=1, sticky=tk.EW, padx=(10, 10))
        
        # Volume percentage label
        volume_label = ttk.Label(volume_frame, text="30%", font=('Segoe UI', 10))
        volume_label.grid(row=0, column=2, sticky=tk.W)
        
        # Update volume label when scale changes
        def update_volume_label(*args):
            volume_percent = int(self.profile_vars['music_volume'].get() * 100)
            volume_label.config(text=f"{volume_percent}%")
        
        self.profile_vars['music_volume'].trace('w', update_volume_label)
        
        # Volume description
        volume_desc = ttk.Label(volume_frame, text="Adjust background music volume only (video audio remains at 100%)", 
                               font=('Segoe UI', 9), foreground='gray')
        volume_desc.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=(10, 0), pady=(5, 0))
        
        # Set up change tracking for all profile variables
        self.setup_change_tracking()
    
    def show_placeholder(self):
        """Show the placeholder message and hide the editor"""
        if hasattr(self, 'editor_frame'):
            self.editor_frame.pack_forget()
        if hasattr(self, 'placeholder_frame'):
            self.placeholder_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
            # Force update to ensure the frame is shown
            self.placeholder_frame.update_idletasks()
    
    def show_editor(self):
        """Show the editor and hide the placeholder message"""
        if hasattr(self, 'placeholder_frame'):
            self.placeholder_frame.pack_forget()
        if hasattr(self, 'editor_frame'):
            self.editor_frame.pack(fill=tk.BOTH, expand=True)
    
    def setup_processing_tab(self):
        """Setup the processing tab"""
        # Configure tab for responsive layout
        self.processing_frame.columnconfigure(0, weight=1)
        self.processing_frame.rowconfigure(1, weight=1)
        
        # Individual channel control buttons
        btn_frame = ttk.Frame(self.processing_frame)
        btn_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(15, 10))
        btn_frame.columnconfigure(4, weight=1)  # Add flexible space
        
        # Store button references for dynamic text updates
        self.process_selected_button = ttk.Button(btn_frame, text="▶️ Process Selected Channel", 
                  command=self.process_selected_channel, style="Accent.TButton")
        self.process_selected_button.grid(row=0, column=0, padx=(0, 10))
        
        self.test_selected_button = ttk.Button(btn_frame, text="🧪 Test Selected Channel", 
                  command=self.test_selected_channel, style="TButton")
        self.test_selected_button.grid(row=0, column=1, padx=(0, 10))
        
        ttk.Button(btn_frame, text="🔄 Refresh Status", 
                  command=self.refresh_channel_status, style="TButton").grid(row=0, column=2, padx=(0, 10))
        ttk.Button(btn_frame, text="📊 View Upload History", 
                  command=self.view_upload_history, style="TButton").grid(row=0, column=3)
        
        # Right side - Bulk processing buttons
        ttk.Button(btn_frame, text="🧪 Test All Channels", 
                  command=self.test_all_channels, style="TButton").grid(row=0, column=6)
        ttk.Button(btn_frame, text="🚀 Process All Channels", 
                  command=self.process_all_channels, style="Accent.TButton").grid(row=0, column=5, padx=(0, 10))
        
        # Channel list frame
        list_frame = ttk.Frame(self.processing_frame)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # Create treeview for channels
        columns = ('Channel', 'Subreddit', 'Startup', 'Last Processed', 'Status')
        self.channels_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)
        
        for col in columns:
            self.channels_tree.heading(col, text=col)
            if col == 'Channel':
                self.channels_tree.column(col, width=200, minwidth=150)
            elif col == 'Startup':
                self.channels_tree.column(col, width=80, minwidth=80)
            else:
                self.channels_tree.column(col, width=150, minwidth=100)
            
        
        # Scrollbar for treeview
        tree_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.channels_tree.yview)
        self.channels_tree.configure(yscrollcommand=tree_scroll.set)
        
        # Grid treeview and scrollbar
        self.channels_tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll.grid(row=0, column=1, sticky="ns")
        
        # Bind selection change event to update button text
        self.channels_tree.bind('<<TreeviewSelect>>', self.on_channel_selection_change)
        
        for col in columns:
            self.channels_tree.heading(col, text=col)
            if col == 'Channel':
                self.channels_tree.column(col, width=200, minwidth=150)
            elif col == 'Startup':
                self.channels_tree.column(col, width=80, minwidth=80)
            else:
                self.channels_tree.column(col, width=150, minwidth=100)
        
        # Scrollbar for treeview
        tree_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.channels_tree.yview)
        self.channels_tree.configure(yscrollcommand=tree_scroll.set)
        
        # Grid treeview and scrollbar
        self.channels_tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll.grid(row=0, column=1, sticky="ns")
        
        self.refresh_channel_status()
    
    def setup_startup_tab(self):
        """Setup the startup management tab"""
        # Configure tab for responsive layout
        self.startup_frame.columnconfigure(0, weight=1)
        self.startup_frame.rowconfigure(0, weight=1)
        
        # Main container with padding
        main_container = ttk.Frame(self.startup_frame)
        main_container.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        main_container.columnconfigure(0, weight=1)
        main_container.rowconfigure(2, weight=1)
        
        # Title and description
        title_frame = ttk.Frame(main_container)
        title_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        
        ttk.Label(title_frame, text="🌅 Startup Management", 
                 font=('Segoe UI', 18, 'bold')).pack(anchor=tk.W)
        ttk.Label(title_frame, text="Channels marked for startup will run automatically when Windows starts", 
                 font=('Segoe UI', 11), foreground='gray').pack(anchor=tk.W, pady=(5, 0))
        
        # Status and action bar
        status_frame = ttk.Frame(main_container)
        status_frame.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        status_frame.columnconfigure(0, weight=1)
        
        # Status indicator (left side)
        status_left = ttk.Frame(status_frame)
        status_left.grid(row=0, column=0, sticky="ew")
        
        self.startup_status_frame = ttk.Frame(status_left)
        self.startup_status_frame.pack(side=tk.LEFT)
        
        self.task_status_icon = ttk.Label(self.startup_status_frame, text="❓", font=('Segoe UI', 14))
        self.task_status_icon.pack(side=tk.LEFT, padx=(0, 10))
        
        status_text_frame = ttk.Frame(self.startup_status_frame)
        status_text_frame.pack(side=tk.LEFT)
        
        self.task_status_title = ttk.Label(status_text_frame, text="Checking startup status...", 
                                          font=('Segoe UI', 12, 'bold'))
        self.task_status_title.pack(anchor=tk.W)
        
        self.startup_status_label = ttk.Label(status_text_frame, text="Please wait...", 
                                             font=('Segoe UI', 10), foreground='#666666')
        self.startup_status_label.pack(anchor=tk.W)
        
        # Action buttons (right side)
        action_frame = ttk.Frame(status_frame)
        action_frame.grid(row=0, column=1, sticky="e")
        
        ttk.Button(action_frame, text="✅ Enable Selected", 
                  command=self.enable_startup_for_selected, style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(action_frame, text="❌ Disable Selected", 
                  command=self.disable_startup_for_selected, style="Danger.TButton").pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(action_frame, text="💾 Save Changes", 
                  command=self.save_profiles, style="Success.TButton").pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(action_frame, text="🚀 Run Now", 
                  command=self.manual_run_startup, style="TButton").pack(side=tk.LEFT)
        
        # Startup channels list
        list_frame = ttk.LabelFrame(main_container, text="📋 Startup-Enabled Channels", padding=15)
        list_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 20))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # Removed old status indicator - now in header
        
        # Remove old sections - update treecols
        startup_columns = ('Channel', 'Subreddit', 'Status')
        self.startup_tree = ttk.Treeview(list_frame, columns=startup_columns, show='headings', height=12)
        
        for col in startup_columns:
            self.startup_tree.heading(col, text=col)
            if col == 'Channel':
                self.startup_tree.column(col, width=300)
            elif col == 'Subreddit':
                self.startup_tree.column(col, width=200)
            else:
                self.startup_tree.column(col, width=150)
        
        startup_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.startup_tree.yview)
        self.startup_tree.configure(yscrollcommand=startup_scroll.set)
        
        self.startup_tree.grid(row=0, column=0, sticky="nsew")
        startup_scroll.grid(row=0, column=1, sticky="ns")
        
        # Bind double-click to toggle startup status
        self.startup_tree.bind("<Double-1>", self.on_startup_tree_double_click)
        
        # Bottom info panel
        info_frame = ttk.Frame(main_container)
        info_frame.grid(row=3, column=0, sticky="ew")
        
        ttk.Label(info_frame, text="💡 Select a channel above and use the Enable/Disable buttons to manage startup settings. The startup script updates automatically when profiles are saved.", 
                 font=('Segoe UI', 10), foreground='#666666').pack(anchor=tk.W)
        
        # Initialize the display
        self.refresh_startup_display()
        
        # Store original startup states for change tracking
        self.store_original_startup_states()
    
    def refresh_startup_display(self):
        """Refresh the startup management display"""
        # Clear existing items
        for item in self.startup_tree.get_children():
            self.startup_tree.delete(item)
        
        # Get startup-enabled profiles count and total uploads
        startup_profiles = [p for p in self.profiles.values() if p.get('run_on_startup', False)]
        startup_count = len(startup_profiles)
        total_uploads = sum(p.get('daily_upload_limit', 1) for p in startup_profiles)
        
        # Update status
        if startup_count == 0:
            status_text = "No startup channels configured"
            status_color = '#666666'
        else:
            status_text = f"{startup_count} channel{'s' if startup_count != 1 else ''} enabled for startup ({total_uploads} total uploads)"
            status_color = '#00aa00'
        
        # Add unsaved changes indicator
        if hasattr(self, 'has_unsaved_startup_changes') and self.has_unsaved_startup_changes:
            status_text += " (unsaved changes)"
            status_color = '#ff6600'  # Orange for unsaved changes
        
        self.startup_status_label.config(text=status_text, foreground=status_color)
        
        # Populate ALL profiles (not just startup-enabled ones)
        for name, profile in self.profiles.items():
            subreddit = profile.get('subreddit', 'Not set')
            if subreddit:
                subreddit = f"r/{subreddit}"
            
            # Determine status based on startup setting and token availability
            is_startup_enabled = profile.get('run_on_startup', False)
            token_file = profile.get('yt_token', '')
            has_token = token_file and os.path.exists(os.path.join(os.path.dirname(__file__), "tokens", token_file))
            
            if is_startup_enabled:
                if has_token:
                    status = "✅ Enabled & Ready"
                else:
                    status = "⚠️ Enabled (No Token)"
            else:
                status = "❌ Not Enabled"
            
            self.startup_tree.insert('', 'end', values=(name, subreddit, status))
        
        # Check Windows Task Scheduler status
        self.check_windows_task_status()
    
    def check_windows_task_status(self):
        """Check if Windows Startup batch file exists"""
        try:
            # Check for the batch file in the Windows Startup folder
            startup_folder = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
            batch_file_path = os.path.join(startup_folder, 'YouTubeShortsBot.bat')
            
            if os.path.exists(batch_file_path):
                # Batch file exists
                self.task_status_icon.config(text="✅")
                self.task_status_title.config(text="Startup Script Active")
            else:
                # Batch file doesn't exist
                self.task_status_icon.config(text="❌")
                self.task_status_title.config(text="Startup Script Missing")
                
        except Exception as e:
            # Error checking startup folder
            self.task_status_icon.config(text="⚠️")
            self.task_status_title.config(text="Cannot Check Startup Status")
    
    def refresh_startup_status(self):
        """Refresh the startup status display"""
        self.refresh_startup_display()
        self.log_message("🔄 Startup status refreshed")
    
    def enable_startup_for_selected(self):
        """Enable startup for the selected channel in the startup tree"""
        selection = self.startup_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a channel to enable for startup.")
            return
        
        # Get the selected channel name
        item = self.startup_tree.item(selection[0])
        channel_name = item['values'][0]
        
        # Debug logging
        self.log_message(f"🔍 Debug: Attempting to enable startup for channel '{channel_name}'")
        
        if channel_name in self.profiles:
            current_startup = self.profiles[channel_name].get('run_on_startup', False)
            self.log_message(f"🔍 Debug: Current startup status for '{channel_name}': {current_startup}")
            
            if current_startup:
                messagebox.showinfo("Info", f"Channel '{channel_name}' is already enabled for startup.")
                return
            
            # Enable startup for this channel
            self.profiles[channel_name]['run_on_startup'] = True
            self.log_message(f"🔍 Debug: Set run_on_startup to True for '{channel_name}'")
            
            # Mark as unsaved change instead of immediately saving
            self.has_unsaved_startup_changes = True
            self.refresh_startup_display()
            
            self.log_message(f"✅ Enabled startup for channel '{channel_name}' (unsaved)")
            self.log_message("💾 Remember to save your changes!")
        else:
            self.log_message(f"🔍 Debug: Channel '{channel_name}' not found in profiles. Available profiles: {list(self.profiles.keys())}")
            messagebox.showerror("Error", f"Channel '{channel_name}' not found in profiles.")
    
    def disable_startup_for_selected(self):
        """Disable startup for the selected channel in the startup tree"""
        selection = self.startup_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a channel to disable from startup.")
            return
        
        # Get the selected channel name
        item = self.startup_tree.item(selection[0])
        channel_name = item['values'][0]
        
        # Debug logging
        self.log_message(f"🔍 Debug: Attempting to disable startup for channel '{channel_name}'")
        
        if channel_name in self.profiles:
            current_startup = self.profiles[channel_name].get('run_on_startup', False)
            self.log_message(f"🔍 Debug: Current startup status for '{channel_name}': {current_startup}")
            
            # Check if it's currently enabled
            if not current_startup:
                messagebox.showinfo("Info", f"Channel '{channel_name}' is already disabled for startup.")
                return
            
            # Disable startup for this channel
            self.profiles[channel_name]['run_on_startup'] = False
            self.log_message(f"🔍 Debug: Set run_on_startup to False for '{channel_name}'")
            
            # Mark as unsaved change instead of immediately saving
            self.has_unsaved_startup_changes = True
            self.refresh_startup_display()
            
            self.log_message(f"❌ Disabled startup for channel '{channel_name}' (unsaved)")
            self.log_message("💾 Remember to save your changes!")
        else:
            self.log_message(f"🔍 Debug: Channel '{channel_name}' not found in profiles. Available profiles: {list(self.profiles.keys())}")
            messagebox.showerror("Error", f"Channel '{channel_name}' not found in profiles.")
    
    def on_startup_tree_double_click(self, event):
        """Handle double-click on startup tree to toggle startup status"""
        selection = self.startup_tree.selection()
        if not selection:
            return
        
        # Get the selected channel name and current status
        item = self.startup_tree.item(selection[0])
        channel_name = item['values'][0]
        status = item['values'][2]
        
        if channel_name in self.profiles:
            current_startup = self.profiles[channel_name].get('run_on_startup', False)
            
            # Toggle the startup setting
            if current_startup:
                self.disable_startup_for_selected()
            else:
                self.enable_startup_for_selected()
    
    def view_startup_logs(self):
        """View startup-related logs"""
        # Switch to logs tab and filter for startup logs
        self.notebook.select(3)  # Logs tab is index 3
        self.log_message("📊 Viewing startup logs...")
        # TODO: Implement log filtering for startup entries
    
    def remove_windows_startup(self):
        """Remove the Windows Startup batch file"""
        try:
            # Get the batch file path
            startup_folder = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
            batch_file_path = os.path.join(startup_folder, 'YouTubeShortsBot.bat')
            
            if os.path.exists(batch_file_path):
                os.remove(batch_file_path)
                self.log_message("❌ Windows startup batch file removed successfully")
                messagebox.showinfo("Success", "Windows startup batch file has been removed.\n\nAutomatic startup is now disabled.")
            else:
                self.log_message("⚠️ Startup batch file not found")
                messagebox.showwarning("Not Found", "No startup batch file was found to remove.")
                
        except Exception as e:
            self.log_message(f"❌ Error removing startup batch file: {str(e)}")
            messagebox.showerror("Error", f"Error removing startup batch file:\n{str(e)}")
        
        # Refresh status
        self.check_windows_task_status()
    
    def view_task_details(self):
        """View startup batch file details"""
        try:
            # Get the batch file path
            startup_folder = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
            batch_file_path = os.path.join(startup_folder, 'YouTubeShortsBot.bat')
            
            if os.path.exists(batch_file_path):
                # Read the batch file content
                with open(batch_file_path, 'r') as f:
                    batch_content = f.read()
                
                # Create a dialog to show batch file details
                dialog = tk.Toplevel(self.root)
                dialog.title("Startup Batch File Details")
                dialog.geometry("700x500")
                dialog.configure(bg='#f8f9fa')
                dialog.transient(self.root)
                dialog.grab_set()
                
                # Center dialog
                dialog.update_idletasks()
                x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
                y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
                dialog.geometry(f"+{x}+{y}")
                
                # Header info
                header_frame = ttk.Frame(dialog)
                header_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
                
                ttk.Label(header_frame, text="Startup Batch File Information", 
                         font=('Segoe UI', 14, 'bold')).pack(anchor=tk.W)
                ttk.Label(header_frame, text=f"Location: {batch_file_path}", 
                         font=('Segoe UI', 9), foreground='gray').pack(anchor=tk.W, pady=(5, 0))
                
                # Create text widget with scrollbar
                text_frame = ttk.Frame(dialog)
                text_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
                
                text_widget = tk.Text(text_frame, wrap=tk.WORD, font=('Consolas', 9))
                scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
                text_widget.configure(yscrollcommand=scrollbar.set)
                
                text_widget.pack(side="left", fill="both", expand=True)
                scrollbar.pack(side="right", fill="y")
                
                text_widget.insert('1.0', batch_content)
                text_widget.config(state='disabled')
                
                # Buttons
                btn_frame = ttk.Frame(dialog)
                btn_frame.pack(fill=tk.X, padx=20, pady=(10, 20))
                
                ttk.Button(btn_frame, text="📁 Open Startup Folder", 
                          command=lambda: os.startfile(startup_folder), style="TButton").pack(side=tk.LEFT, padx=(0, 10))
                ttk.Button(btn_frame, text="✏️ Edit File", 
                          command=lambda: os.startfile(batch_file_path), style="TButton").pack(side=tk.LEFT, padx=(0, 10))
                ttk.Button(btn_frame, text="Close", command=dialog.destroy, style="TButton").pack(side=tk.RIGHT)
                
            else:
                messagebox.showwarning("Batch File Not Found", "No startup batch file found for YouTube Shorts Bot.")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to get batch file details:\n{str(e)}")
    
    def open_startup_logs_folder(self):
        """Open the folder containing startup logs"""
        try:
            logs_folder = os.path.dirname(__file__)
            os.startfile(logs_folder)
            self.log_message("📁 Opened logs folder")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open logs folder:\n{str(e)}")
    
    def edit_task_schedule(self):
        """Open the startup batch file for editing"""
        try:
            startup_folder = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
            batch_file_path = os.path.join(startup_folder, 'YouTubeShortsBot.bat')
            
            if os.path.exists(batch_file_path):
                os.startfile(batch_file_path)
                self.log_message("✏️ Opened startup batch file for editing")
                messagebox.showinfo("Batch File Editor", "The startup batch file has been opened for editing.\n\nMake sure to save the file after making changes.")
            else:
                messagebox.showwarning("File Not Found", "No startup batch file found to edit.\n\nPlease setup Windows startup first.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open batch file for editing:\n{str(e)}")
    
    def troubleshoot_startup(self):
        """Show troubleshooting guide for startup issues"""
        dialog = tk.Toplevel(self.root)
        dialog.title("🔧 Startup Troubleshooting")
        dialog.geometry("700x600")
        dialog.configure(bg='#f8f9fa')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Create scrollable content
        canvas = tk.Canvas(dialog, bg='#f8f9fa', highlightthickness=0)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Title
        ttk.Label(scrollable_frame, text="🔧 Startup Troubleshooting Guide", 
                 font=('Segoe UI', 16, 'bold')).pack(pady=(20, 10))
        
        # Troubleshooting sections
        sections = [
            ("Common Issues", [
                "• Channels not processing at startup",
                "• Startup batch file not running",
                "• Token authentication errors",
                "• Script crashes on startup"
            ]),
            ("Quick Fixes", [
                "• Check if channels have 'Run on Startup' enabled",
                "• Verify startup batch file exists in Startup folder",
                "• Ensure client_secrets.json is present",
                "• Test with 'Run Startup Profiles Now' first"
            ]),
            ("Advanced Solutions", [
                "• Run as Administrator if permission errors occur",
                "• Check Windows Event Viewer for startup errors",
                "• Verify Python path in batch file is correct",
                "• Check antivirus isn't blocking the script"
            ]),
            ("Getting Help", [
                "• Check the logs for error messages",
                "• Test individual channels manually first",
                "• Ensure all dependencies are installed",
                "• Contact support with log files if issues persist"
            ])
        ]
        
        for section_title, items in sections:
            section_frame = ttk.LabelFrame(scrollable_frame, text=section_title, padding=15)
            section_frame.pack(fill=tk.X, padx=20, pady=10)
            
            for item in items:
                ttk.Label(section_frame, text=item, font=('Segoe UI', 10)).pack(anchor=tk.W, pady=2)
        
        # Close button
        ttk.Button(scrollable_frame, text="Close", command=dialog.destroy, style="TButton").pack(pady=20)
        
        # Pack scrollable content
        canvas.pack(side="left", fill="both", expand=True, padx=(20, 0), pady=20)
        scrollbar.pack(side="right", fill="y", pady=20)
        
        # Bind mousewheel
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind("<MouseWheel>", _on_mousewheel)
    
    def setup_logs_tab(self):
        """Setup the logs and status tab"""
        # Configure tab for responsive layout
        self.logs_frame.columnconfigure(0, weight=1)
        self.logs_frame.rowconfigure(2, weight=1)
        
        # Status frame with more detailed info
        status_frame = ttk.LabelFrame(self.logs_frame, text="Current Status & System Info")
        status_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        status_frame.columnconfigure(0, weight=1)
        
        # Current status
        status_info_frame = ttk.Frame(status_frame)
        status_info_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        
        ttk.Label(status_info_frame, text="Status:", font=('Segoe UI', 10, 'bold')).pack(side=tk.LEFT)
        self.status_label = ttk.Label(status_info_frame, text="Ready", font=('Segoe UI', 10))
        self.status_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # System info
        system_info_frame = ttk.Frame(status_frame)
        system_info_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        
        # Profile count
        ttk.Label(system_info_frame, text="Profiles:", font=('Segoe UI', 10, 'bold')).pack(side=tk.LEFT)
        self.profiles_count_label = ttk.Label(system_info_frame, text="0 total, 0 startup-enabled", font=('Segoe UI', 10))
        self.profiles_count_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # Update profile count
        self.update_system_info()
        
        # Progress bar
        progress_frame = ttk.Frame(status_frame)
        progress_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        
        ttk.Label(progress_frame, text="Progress:", font=('Segoe UI', 10, 'bold')).pack(side=tk.LEFT)
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        
        # Logs frame
        logs_frame = ttk.LabelFrame(self.logs_frame, text="Activity Logs")
        logs_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        logs_frame.columnconfigure(0, weight=1)
        logs_frame.rowconfigure(1, weight=1)
        
        # Add help text
        help_frame = ttk.Frame(logs_frame)
        help_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 0))
        
        help_text = "🚀 Production uploads • 🧪 Test uploads (private) • 🌅 Startup processing • 📋 Channel details"
        ttk.Label(help_frame, text=help_text, font=('Segoe UI', 9), foreground='gray').pack(side=tk.LEFT)
        
        self.log_text = scrolledtext.ScrolledText(logs_frame, height=18, width=80, font=('Consolas', 9))
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        # Log controls
        log_controls = ttk.Frame(self.logs_frame)
        log_controls.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        log_controls.columnconfigure(0, weight=1)
        
        # Left side - regular controls
        left_controls = ttk.Frame(log_controls)
        left_controls.grid(row=0, column=0, sticky="ew")
        
        ttk.Button(left_controls, text="❌ Clear Logs", command=self.clear_logs, style="Danger.TButton").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(left_controls, text="💾 Save Logs", command=self.save_logs, style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(left_controls, text="📁 Open Log File", command=self.open_log_file, style="TButton").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(left_controls, text="🔄 Refresh Info", command=self.update_system_info, style="TButton").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(left_controls, text="🔍 Debug Profile", command=self.debug_current_profile, style="TButton").pack(side=tk.LEFT)
        
        # Right side - abort control
        right_controls = ttk.Frame(log_controls)
        right_controls.grid(row=0, column=1, sticky="e")
        
        self.abort_button = ttk.Button(right_controls, text="🛑 Abort Process", 
                                     command=self.abort_current_process, state='disabled',
                                     style="Critical.TButton")
        self.abort_button.pack(side=tk.RIGHT)
    
    def sanitize_text_for_utf8(self, text):
        """Sanitize text to prevent UTF-8 encoding issues"""
        if not isinstance(text, str):
            return str(text)
        
        # Remove or replace problematic characters
        try:
            # Try to encode/decode to check for issues
            text.encode('utf-8').decode('utf-8')
            return text
        except UnicodeDecodeError:
            # Replace problematic characters
            return text.encode('utf-8', 'replace').decode('utf-8')
        except UnicodeEncodeError:
            # Replace problematic characters
            return text.encode('ascii', 'replace').decode('ascii')
    
    def debug_current_profile(self):
        """Debug function to show current profile data"""
        if not self.selected_profile:
            messagebox.showinfo("Debug Profile", "No profile selected")
            return
        
        # Get current UI data
        current_data = self.get_current_profile_data()
        
        # Get saved profile data
        saved_data = self.profiles.get(self.selected_profile, {})
        
        # Read from file to compare with what's actually persisted
        try:
            profiles_file = os.path.join(os.path.dirname(__file__), "profiles.json")
            with open(profiles_file, 'r', encoding='utf-8') as f:
                file_data = json.load(f)
            file_profile = file_data.get(self.selected_profile, {})
        except Exception as e:
            file_profile = {}
        
        # Show detailed comparison
        debug_text = f"Profile: {self.selected_profile}\n\n"
        debug_text += f"UI Hashtags ({len(current_data.get('hashtags', []))}):\n"
        for i, hashtag in enumerate(current_data.get('hashtags', [])):
            debug_text += f"  {i+1}. {hashtag}\n"
        
        debug_text += f"\nMemory Hashtags ({len(saved_data.get('hashtags', []))}):\n"
        for i, hashtag in enumerate(saved_data.get('hashtags', [])):
            debug_text += f"  {i+1}. {hashtag}\n"
        
        debug_text += f"\nFile Hashtags ({len(file_profile.get('hashtags', []))}):\n"
        for i, hashtag in enumerate(file_profile.get('hashtags', [])):
            debug_text += f"  {i+1}. {hashtag}\n"
        
        debug_text += f"\nUnsaved changes flag: {self.has_unsaved_changes}\n"
        debug_text += f"UI != Original: {current_data != self.original_profile_data if hasattr(self, 'original_profile_data') else 'No original data'}\n"
        debug_text += f"Memory != File: {saved_data != file_profile}"
        
        # Show in a dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Profile Debug Info")
        dialog.geometry("600x500")
        dialog.transient(self.root)
        dialog.grab_set()
        
        text_widget = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, font=('Consolas', 10))
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_widget.insert('1.0', debug_text)
        text_widget.config(state='disabled')
        
        ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=10)
    
    def update_system_info(self):
        """Update system information in the logs tab"""
        total_profiles = len(self.profiles)
        startup_profiles = len([p for p in self.profiles.values() if p.get('run_on_startup', False)])
        # Only update if the logs tab has been created
        if hasattr(self, 'profiles_count_label'):
            self.profiles_count_label.config(text=f"{total_profiles} total, {startup_profiles} startup-enabled")
    
    def abort_current_process(self):
        """Abort any currently running process"""
        if self.is_processing:
            # Confirm with user
            result = messagebox.askyesno(
                "Abort Process",
                "Are you sure you want to abort the currently running process?\n\n"
                "This will stop the process immediately and may leave some operations incomplete."
            )
            
            if result:
                self.abort_processing = True
                
                # Stop all period animations immediately
                self.stop_all_animations()
                
                # Update UI immediately
                self.status_label.config(text="Aborting process...")
                self.abort_button.config(state='disabled')
                
                # The actual abort will be handled by the processing threads
                # when they check the abort_processing flag
        else:
            messagebox.showinfo("No Process Running", "No process is currently running to abort.")
    
    def start_processing_mode(self, process_name):
        """Enable processing mode and update UI"""
        self.is_processing = True
        self.abort_processing = False
        if hasattr(self, 'abort_button'):
            self.abort_button.config(state='normal')
        self.log_message(f"🚀 Started: {process_name}")
    
    def end_processing_mode(self, success=True, message=""):
        """Disable processing mode and update UI"""
        self.is_processing = False
        self.abort_processing = False
        
        # Stop all period animations when processing ends
        self.stop_all_animations()
        
        if hasattr(self, 'abort_button'):
            self.abort_button.config(state='disabled')
        
        if success:
            self.status_label.config(text="Ready")
            self.progress_var.set(0)
            # Set main status to ready only if no warnings are shown
            if hasattr(self, 'main_status') and not (self._warning_shown or self._reddit_warning_shown or self._storage_warning_shown):
                self.main_status.config(text="● Ready", foreground='#00aa00')
            if message:
                self.log_message(f"✅ {message}")
        else:
            self.status_label.config(text="Process aborted")
            self.progress_var.set(0)
            # Don't override main status with error if only quota/upload issues
            if message:
                self.log_message(f"❌ {message}")
            # Don't log another abort message here since it was already logged
    
    def refresh_profile_list(self):
        """Refresh the profile listbox"""
        self.profile_listbox.delete(0, tk.END)
        
        # Create a mapping from display order to profile key
        self._profile_display_map = {}
        
        for i, (profile_key, profile_data) in enumerate(self.profiles.items()):
            # Use the label if it exists, otherwise fall back to the profile key
            display_name = profile_data.get('label', profile_key)
            self.profile_listbox.insert(tk.END, display_name)
            # Store the mapping from listbox index to profile key
            self._profile_display_map[i] = profile_key
        
        # If no profiles exist or no profile is selected, show placeholder
        if not self.profiles or not hasattr(self, 'selected_profile') or not self.selected_profile:
            self.show_placeholder()
        
        # Update system info only if the logs tab has been created
        if hasattr(self, 'profiles_count_label'):
            self.update_system_info()

    def on_profile_select(self, event):
        """Handle profile selection"""
        # Ignore selection events if a dialog is open
        if self._dialog_open:
            return "break"
            
        selection = self.profile_listbox.curselection()
        if not selection:
            # No profile selected - show placeholder
            self.selected_profile = None
            self.show_placeholder()
            return
        
        # Get the actual profile key using the display mapping
        selected_index = selection[0]
        if hasattr(self, '_profile_display_map') and selected_index in self._profile_display_map:
            new_profile_key = self._profile_display_map[selected_index]
        else:
            # Fallback to old behavior if mapping doesn't exist
            new_profile_key = self.profile_listbox.get(selected_index)
        
        # If selecting the same profile, do nothing
        if hasattr(self, 'selected_profile') and self.selected_profile == new_profile_key:
            return
        
        # Check for unsaved changes before switching
        if hasattr(self, 'selected_profile') and self.selected_profile:
            # Update unsaved changes flag based on actual comparison
            self.has_unsaved_changes = self.check_for_unsaved_changes()
            
            if not self.prompt_save_changes("switch to another profile"):
                # User cancelled, revert selection
                self.select_profile_in_list(self.selected_profile)
                return
        
        # Proceed with profile switch
        self.selected_profile = new_profile_key
        self.load_profile_to_editor(new_profile_key)
    
    def select_profile_in_list(self, profile_key):
        """Select a specific profile in the listbox without triggering events"""
        if not hasattr(self, 'profile_listbox'):
            return
        
        # Find the profile using the display mapping
        if hasattr(self, '_profile_display_map'):
            for index, mapped_profile_key in self._profile_display_map.items():
                if mapped_profile_key == profile_key:
                    self.profile_listbox.selection_clear(0, tk.END)
                    self.profile_listbox.selection_set(index)
                    break
        else:
            # Fallback to old behavior if mapping doesn't exist
            for i in range(self.profile_listbox.size()):
                if self.profile_listbox.get(i) == profile_key:
                    self.profile_listbox.selection_clear(0, tk.END)
                    self.profile_listbox.selection_set(i)
                    break
    
    def load_profile_to_editor(self, profile_name):
        """Load profile data into the editor"""
        if profile_name not in self.profiles:
            return
        
        # Set loading flag to prevent change tracking during load
        self.loading_profile = True
        
        # Show the editor and hide placeholder
        self.show_editor()
        
        profile = self.profiles[profile_name]
        
        # Temporarily disable change tracking while loading
        # Clear any existing trace callbacks
        if hasattr(self, 'profile_vars'):
            for var in self.profile_vars.values():
                if hasattr(var, 'trace_info'):
                    # Remove all existing traces
                    for trace_id in var.trace_info():
                        try:
                            var.trace_vdelete('w', trace_id)
                        except:
                            pass
        
        # Load basic fields
        self.profile_vars['label'].set(profile.get('label', ''))
        self.profile_vars['subreddit'].set(profile.get('subreddit', ''))
        self.profile_vars['yt_token'].set(profile.get('yt_token', ''))
        self.profile_vars['music_dir'].set(profile.get('music_dir', ''))
        self.profile_vars['horizontal_zoom'].set(profile.get('horizontal_zoom', 1.6))
        self.profile_vars['run_on_startup'].set(profile.get('run_on_startup', False))
        self.profile_vars['daily_upload_limit'].set(profile.get('daily_upload_limit', 1))
        
        # Load hashtags into listbox
        self.hashtags_listbox.delete(0, tk.END)
        hashtags = profile.get('hashtags', [])
        for hashtag in hashtags:
            self.hashtags_listbox.insert(tk.END, hashtag)
        
        # Load sample titles into listbox
        self.titles_listbox.delete(0, tk.END)
        titles = profile.get('sample_titles', [])
        for title in titles:
            self.titles_listbox.insert(tk.END, title)
        
        # Load font settings
        font_config = profile.get('font', {})
        self.profile_vars['font_path'].set(font_config.get('path', 'C:\\Windows\\Fonts\\impact.ttf'))
        self.profile_vars['font_size'].set(font_config.get('size', 70))
        self.profile_vars['text_position_y'].set(font_config.get('text_position_y', 320))
        
        # Load video selection settings
        video_selection = profile.get('video_selection', {})
        self.profile_vars['video_sort_method'].set(video_selection.get('sort_method', 'top_month'))
        self.profile_vars['enable_fallback'].set(video_selection.get('enable_fallback', True))
        
        # Load music settings (NEW) - convert old format to new format if needed
        music_mode = profile.get('music_mode', 'smart')  # Default to smart mode
        
        # Handle migration from old format
        if 'enable_music' in profile or 'auto_detect_silence' in profile:
            enable_music = profile.get('enable_music', True)
            auto_detect = profile.get('auto_detect_silence', True)
            
            if not enable_music:
                music_mode = 'disabled'
            elif enable_music and not auto_detect:
                music_mode = 'always'
            else:
                music_mode = 'smart'
        
        self.profile_vars['music_mode'].set(music_mode)
        
        # Load music volume setting
        music_volume = profile.get('music_volume', 0.3)  # Default to 30% volume
        self.profile_vars['music_volume'].set(music_volume)
        
        # Store original data for change tracking BEFORE setting up tracking
        self.store_original_profile_data()
        
        # Clear loading flag to re-enable change tracking BEFORE setting up tracking
        self.loading_profile = False
        
        # Re-enable change tracking AFTER clearing the loading flag
        self.setup_change_tracking()
        
        # Force clear unsaved changes flag as final step (safeguard against any race conditions)
        self.has_unsaved_changes = False
        self.update_save_indicator()
    
    def setup_change_tracking(self):
        """Set up change tracking for profile variables with deferred execution to prevent GUI issues"""
        if not hasattr(self, 'profile_vars'):
            return
        
        def safe_track_changes(*args):
            """Safely track changes using after_idle to prevent event loops"""
            # Additional safety check in the deferred callback
            if getattr(self, 'loading_profile', False):
                return
            # Use after_idle to defer the change tracking to prevent GUI freezing
            self.root.after_idle(self.track_profile_changes)
        
        # Add trace to all profile variables with safe tracking
        for var in self.profile_vars.values():
            if hasattr(var, 'trace'):
                var.trace('w', safe_track_changes)
    
    def add_hashtag(self):
        """Add new hashtag"""
        self._dialog_open = True
        hashtag = tk.simpledialog.askstring("Add Hashtag", "Enter hashtag (with or without #):")
        self._dialog_open = False
        
        if hashtag:
            if not hashtag.startswith('#'):
                hashtag = '#' + hashtag
            self.hashtags_listbox.insert(tk.END, hashtag)
            self.track_profile_changes()  # Mark as changed
            self.log_message(f"➕ Added hashtag: {hashtag}")
    
    def edit_hashtag(self):
        """Edit selected hashtag"""
        selection = self.hashtags_listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a hashtag to edit")
            return
        
        current = self.hashtags_listbox.get(selection[0])
        
        self._dialog_open = True
        new_hashtag = tk.simpledialog.askstring("Edit Hashtag", "Edit hashtag:", initialvalue=current)
        self._dialog_open = False
        
        if new_hashtag:
            if not new_hashtag.startswith('#'):
                new_hashtag = '#' + new_hashtag
            self.hashtags_listbox.delete(selection[0])
            self.hashtags_listbox.insert(selection[0], new_hashtag)
            self.track_profile_changes()  # Mark as changed
            self.log_message(f"✏️ Updated hashtag: {current} → {new_hashtag}")
    
    def remove_hashtag(self):
        """Remove selected hashtag"""
        selection = self.hashtags_listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a hashtag to remove")
            return
        
        removed_hashtag = self.hashtags_listbox.get(selection[0])
        self.hashtags_listbox.delete(selection[0])
        self.track_profile_changes()  # Mark as changed
        self.log_message(f"❌ Removed hashtag: {removed_hashtag}")
    
    def add_title(self):
        """Add new sample title"""
        self._dialog_open = True
        title = tk.simpledialog.askstring("Add Title", "Enter sample title:")
        self._dialog_open = False
        
        if title:
            self.titles_listbox.insert(tk.END, title)
            self.track_profile_changes()  # Mark as changed
    
    def edit_title(self):
        """Edit selected title"""
        selection = self.titles_listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a title to edit")
            return
        
        current = self.titles_listbox.get(selection[0])
        
        self._dialog_open = True
        new_title = tk.simpledialog.askstring("Edit Title", "Edit title:", initialvalue=current)
        self._dialog_open = False
        
        if new_title:
            self.titles_listbox.delete(selection[0])
            self.titles_listbox.insert(selection[0], new_title)
            self.track_profile_changes()  # Mark as changed
    
    def remove_title(self):
        """Remove selected title"""
        selection = self.titles_listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a title to remove")
            return
        self.titles_listbox.delete(selection[0])
        self.track_profile_changes()  # Mark as changed
    
    def migrate_processed_files(self, old_profile_key, old_label, new_profile_key, new_label):
        """Migrate processed files when profile key or label changes"""
        try:
            processed_dir = os.path.join(os.path.dirname(__file__), "processed")
            if not os.path.exists(processed_dir):
                return
            
            # Generate possible old filenames based on old key and label
            old_filenames = []
            if old_label:
                old_filenames.append(f"processed_{old_label}.json")
            if old_profile_key and old_profile_key != old_label:
                old_filenames.append(f"processed_{old_profile_key}.json")
            
            # Generate new filename based on new label
            new_filename = f"processed_{new_label}.json"
            new_filepath = os.path.join(processed_dir, new_filename)
            
            # Look for existing processed files
            migrated = False
            for old_filename in old_filenames:
                old_filepath = os.path.join(processed_dir, old_filename)
                if os.path.exists(old_filepath):
                    try:
                        # Read existing data
                        with open(old_filepath, 'r', encoding='utf-8') as f:
                            existing_data = json.load(f)
                        
                        # Check if new file already exists
                        if os.path.exists(new_filepath):
                            # Merge with existing new file
                            with open(new_filepath, 'r', encoding='utf-8') as f:
                                new_data = json.load(f)
                            
                            # Merge records, avoiding duplicates
                            existing_ids = {record.get('id') for record in new_data}
                            for record in existing_data:
                                if record.get('id') not in existing_ids:
                                    new_data.append(record)
                            
                            # Save merged data
                            with open(new_filepath, 'w', encoding='utf-8') as f:
                                json.dump(new_data, f, indent=2, ensure_ascii=False)
                            
                            self.log_message(f"📋 Merged upload history: {old_filename} → {new_filename}")
                        else:
                            # Simply rename/copy the file
                            with open(new_filepath, 'w', encoding='utf-8') as f:
                                json.dump(existing_data, f, indent=2, ensure_ascii=False)
                            
                            self.log_message(f"📋 Migrated upload history: {old_filename} → {new_filename}")
                        
                        # Remove old file to prevent confusion
                        os.remove(old_filepath)
                        self.log_message(f"🗑️ Removed old upload history file: {old_filename}")
                        migrated = True
                        break  # Only migrate the first found file
                        
                    except Exception as e:
                        self.log_message(f"⚠️ Failed to migrate {old_filename}: {str(e)}")
            
            if not migrated:
                self.log_message(f"📋 No upload history found to migrate for '{old_label}' → '{new_label}'")
                
        except Exception as e:
            self.log_message(f"❌ Failed to migrate processed files: {str(e)}")

    def save_profile_from_editor(self, log_changes=True):
        """Save profile from editor back to profiles dict"""
        if not self.selected_profile:
            return
        
        # Store old label for token rename detection
        old_profile = self.profiles.get(self.selected_profile, {})
        old_label = old_profile.get('label', '')
        
        # Get current data from the UI
        hashtags = []
        for i in range(self.hashtags_listbox.size()):
            hashtags.append(self.hashtags_listbox.get(i))
        
        titles = []
        for i in range(self.titles_listbox.size()):
            titles.append(self.titles_listbox.get(i))
        
        # Build new profile data
        new_profile = {
            'label': self.profile_vars['label'].get(),
            'subreddit': self.profile_vars['subreddit'].get(),
            'yt_token': self.profile_vars['yt_token'].get(),
            'music_dir': self.profile_vars['music_dir'].get(),
            'horizontal_zoom': self.profile_vars['horizontal_zoom'].get(),
            'run_on_startup': self.profile_vars['run_on_startup'].get(),
            'daily_upload_limit': self.profile_vars['daily_upload_limit'].get(),
            'hashtags': hashtags,
            'sample_titles': titles,
            'video_selection': {
                'sort_method': self.profile_vars['video_sort_method'].get(),
                'enable_fallback': self.profile_vars['enable_fallback'].get()
            },
            'font': {
                'path': self.profile_vars['font_path'].get(),
                'size': self.profile_vars['font_size'].get(),
                'text_position_y': self.profile_vars['text_position_y'].get()
            },
            # Music settings (NEW) - simplified to just music_mode and volume
            'music_mode': self.profile_vars['music_mode'].get(),
            'music_volume': self.profile_vars['music_volume'].get()
        }
        
        new_label = new_profile['label']
        
        # Compare with existing profile to see if there are changes
        has_changes = new_profile != old_profile
        
        # Check specifically for hashtag changes for detailed logging
        old_hashtags = set(old_profile.get('hashtags', []))
        new_hashtags = set(hashtags)
        hashtag_changes = old_hashtags != new_hashtags
        
        # CRITICAL FIX: Handle profile key rename when label changes
        if old_label and new_label and old_label != new_label:
            # Generate new profile key from new label
            safe_new_key = new_label.lower().replace(" ", "_").replace("-", "_")
            safe_new_key = "".join(c for c in safe_new_key if c.isalnum() or c == "_")
            
            # Check if the new key conflicts with existing profiles
            if safe_new_key in self.profiles and safe_new_key != self.selected_profile:
                # If there's a conflict, add a suffix
                counter = 1
                while f"{safe_new_key}_{counter}" in self.profiles:
                    counter += 1
                safe_new_key = f"{safe_new_key}_{counter}"
            
            # Remove old profile key and add new one
            if safe_new_key != self.selected_profile:
                self.log_message(f"🔑 Renaming profile key: '{self.selected_profile}' → '{safe_new_key}'")
                self.profiles[safe_new_key] = new_profile
                del self.profiles[self.selected_profile]
                
                # Update selected profile reference
                old_selected = self.selected_profile
                self.selected_profile = safe_new_key
                
                self.log_message(f"✅ Profile key updated to match label")
                
                # MIGRATION FIX: Handle processed file migration when profile key/label changes
                self.migrate_processed_files(old_selected, old_label, safe_new_key, new_label)
            else:
                # Update profile with same key
                self.profiles[self.selected_profile] = new_profile
                
                # Check if label changed but key stayed the same - still need to migrate processed files
                if old_label != new_label:
                    self.migrate_processed_files(self.selected_profile, old_label, self.selected_profile, new_label)
        else:
            # Update profile without key change
            self.profiles[self.selected_profile] = new_profile
        
        # Check if label changed and auto-rename token if needed
        if old_label and new_label and old_label != new_label:
            self.log_message(f"🔍 Debug: Label changed from '{old_label}' to '{new_label}' - attempting auto-rename")
            self.auto_rename_token_on_profile_change(old_label, new_label)
            # Get the updated token name from the profile after auto-rename
            updated_token = self.profiles[self.selected_profile].get('yt_token', '')
            if updated_token != self.profile_vars['yt_token'].get():
                # Temporarily disable change tracking during token sync
                old_loading_flag = getattr(self, 'loading_profile', False)
                self.loading_profile = True
                
                self.profile_vars['yt_token'].set(updated_token)
                self.log_message(f"🔍 Debug: Synced GUI field with updated token: {updated_token}")
                
                # Restore loading flag
                self.loading_profile = old_loading_flag
                
                # Also update the new_profile data to reflect the token change
                new_profile['yt_token'] = updated_token
                self.log_message(f"🔍 Debug: Updated new_profile data with token: {updated_token}")
        
        # Reset unsaved changes flag and update indicator
        self.has_unsaved_changes = False
        # Store original data based on the updated profile, not GUI state
        if hasattr(self, 'selected_profile') and self.selected_profile:
            self.original_profile_data = new_profile.copy()
            self.log_message(f"🔍 Debug: Updated original_profile_data with new token")
        
        # Save profiles to disk immediately if there were changes
        if has_changes:
            try:
                profiles_file = os.path.join(os.path.dirname(__file__), "profiles.json")
                with open(profiles_file, 'w', encoding='utf-8') as f:
                    json.dump(self.profiles, f, indent=2, ensure_ascii=False)
                self.log_message(f"💾 Auto-saved profile changes to disk")
            except Exception as e:
                self.log_message(f"❌ Failed to auto-save profiles: {str(e)}")
        
        # Refresh the profile list to show any label changes
        if hasattr(self, 'refresh_profile_list'):
            self.refresh_profile_list()
            # Ensure the current profile remains selected
            self.select_profile_in_list(self.selected_profile)
        
        # Final verification: ensure GUI token field matches profile data
        if hasattr(self, 'profile_vars') and 'yt_token' in self.profile_vars:
            current_profile_token = self.profiles.get(self.selected_profile, {}).get('yt_token', '')
            current_gui_token = self.profile_vars['yt_token'].get()
            if current_profile_token and current_profile_token != current_gui_token:
                self.profile_vars['yt_token'].set(current_profile_token)
                self.log_message(f"🔍 Debug: Final sync - updated GUI token field to match profile: {current_profile_token}")
        
        # Only log if there are actual changes and logging is enabled
        if has_changes and log_changes:
            if hashtag_changes:
                added_hashtags = new_hashtags - old_hashtags
                removed_hashtags = old_hashtags - new_hashtags
                if added_hashtags:
                    self.log_message(f"📝 Added hashtags to '{self.selected_profile}': {', '.join(added_hashtags)}")
                if removed_hashtags:
                    self.log_message(f"📝 Removed hashtags from '{self.selected_profile}': {', '.join(removed_hashtags)}")
            self.log_message(f"✏️ Profile '{self.selected_profile}' updated with {len(hashtags)} hashtags")
    
    def new_profile(self):
        """Create a new profile"""
        # Check for unsaved changes first
        if hasattr(self, 'selected_profile') and self.selected_profile:
            self.has_unsaved_changes = self.check_for_unsaved_changes()
            if not self.prompt_save_changes("create a new profile"):
                return  # User cancelled
        
        self._dialog_open = True
        name = tk.simpledialog.askstring("New Profile", "Enter profile name:")
        self._dialog_open = False
        
        if not name or name in self.profiles:
            if name in self.profiles:
                messagebox.showerror("Error", f"Profile '{name}' already exists!")
            return
        
        # Ask about token handling
        token_choice = messagebox.askyesnocancel(
            "YouTube Token Setup",
            f"Setting up channel: {name}\n\n"
            "Do you want to generate a NEW token for this channel?\n\n"
            "• Click YES if this is a NEW channel (first time setup)\n"
            "• Click NO to use an existing token file\n"
            "• Click CANCEL to abort profile creation"
        )
        
        if token_choice is None:  # User clicked Cancel
            return
        
        if token_choice:  # User wants to generate new token
            auto_token = self.generate_new_token(name)
        else:  # User wants to use existing token
            auto_token = self.select_existing_token(name)
        
        if auto_token is None:  # User cancelled token setup
            return
        
        # Create the profile
        self.profiles[name] = {
            'label': name,
            'subreddit': '',
            'yt_token': auto_token,
            'music_dir': '',
            'horizontal_zoom': 1.5,
            'run_on_startup': False,
            'daily_upload_limit': 1,
            'hashtags': [],
            'sample_titles': [],
            'font': {'path': 'C:\\Windows\\Fonts\\impact.ttf', 'size': 70},
            'music_mode': 'smart',
            'music_volume': 0.3
        }
        self.refresh_profile_list()
        
        # Select the new profile
        profile_list = list(self.profiles.keys())
        if name in profile_list:
            index = profile_list.index(name)
            self.profile_listbox.selection_clear(0, tk.END)
            self.profile_listbox.selection_set(index)
            self.profile_listbox.activate(index)
            self.selected_profile = name
            self.load_profile_to_editor(name)
            
            # Mark as unsaved since this is a new profile that hasn't been saved to disk
            self.has_unsaved_changes = True
            self.update_save_indicator()
        
        token_msg = f" (token: {auto_token})" if auto_token else ""
        self.log_message(f"➕ New profile '{name}' created{token_msg}")
        self.log_message(f"💾 Remember to save changes to persist this profile to disk")
    
    def auto_detect_token_file(self, profile_name):
        """Auto-detect YouTube token file for the profile"""
        # Look for token files in the tokens directory
        tokens_dir = os.path.join(os.path.dirname(__file__), "tokens")
        if not os.path.exists(tokens_dir):
            return ""
        
        # Convert profile name to expected token filename format
        # e.g., "Best Car Collisions" -> "yt_token_best_car_collisions.json"
        safe_name = profile_name.lower().replace(" ", "_").replace("-", "_")
        safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")
        expected_token = f"yt_token_{safe_name}.json"
        
        # Check if the expected token file exists
        token_path = os.path.join(tokens_dir, expected_token)
        if os.path.exists(token_path):
            return expected_token
        
        # If not found, look for any token files and suggest the first one
        try:
            token_files = [f for f in os.listdir(tokens_dir) if f.endswith('.json') and f.startswith('yt_token_')]
            if token_files:
                return token_files[0]  # Return the first available token file
        except:
            pass
        
        return ""
    
    def generate_new_token(self, profile_name):
        """Generate a new YouTube token for the profile"""
        try:
            # Import YouTube OAuth modules
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            
            # Create tokens directory if it doesn't exist
            tokens_dir = os.path.join(os.path.dirname(__file__), "tokens")
            os.makedirs(tokens_dir, exist_ok=True)
            
            # Generate token filename
            safe_name = profile_name.lower().replace(" ", "_").replace("-", "_")
            safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")
            token_filename = f"yt_token_{safe_name}.json"
            token_path = os.path.join(tokens_dir, token_filename)
            
            # Show instructions dialog
            instructions = f"""Setting up YouTube token for: {profile_name}

IMPORTANT: You need the client_secrets.json file for this to work.

Steps:
1. Your browser will open to Google OAuth
2. Sign in to the Google account that owns the YouTube channel
3. Grant permissions to the YouTube API
4. The token will be saved automatically

Token will be saved as: {token_filename}

Ready to proceed?"""
            
            if not messagebox.askyesno("Generate YouTube Token", instructions):
                return None
            
            # Check if client_secrets.json exists
            client_secrets_path = os.path.join(os.path.dirname(__file__), "client_secrets.json")
            if not os.path.exists(client_secrets_path):
                messagebox.showerror(
                    "Missing client_secrets.json", 
                    "client_secrets.json file not found!\n\n"
                    "You need to download this file from Google Cloud Console:\n"
                    "1. Go to console.cloud.google.com\n"
                    "2. Select your project\n"
                    "3. Go to APIs & Services > Credentials\n"
                    "4. Download OAuth 2.0 Client IDs as JSON\n"
                    "5. Rename it to 'client_secrets.json'"
                )
                return None
            
            # YouTube API scopes
            SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
            
            try:
                # Start OAuth flow
                flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)
                credentials = flow.run_local_server(port=0)
                
                # Save credentials to JSON format (compatible with process_videos.py)
                with open(token_path, 'w', encoding='utf-8') as token_file:
                    token_file.write(credentials.to_json())
                
                self.log_message(f"✅ YouTube token generated successfully: {token_filename}")
                messagebox.showinfo(
                    "Token Generated Successfully", 
                    f"YouTube token created: {token_filename}\n\n"
                    f"Channel: {profile_name}\n"
                    f"You can now use this profile to upload videos!"
                )
                
                return token_filename
                
            except Exception as oauth_error:
                messagebox.showerror(
                    "OAuth Error", 
                    f"Failed to generate token: {str(oauth_error)}\n\n"
                    "Make sure:\n"
                    "• client_secrets.json is valid\n"
                    "• YouTube Data API v3 is enabled\n"
                    "• OAuth consent screen is configured"
                )
                return None
                
        except ImportError:
            messagebox.showerror(
                "Missing Dependencies", 
                "Required modules not found!\n\n"
                "Please install:\n"
                "pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client"
            )
            return None
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate token: {str(e)}")
            return None
    
    def select_existing_token(self, profile_name):
        """Let user select an existing token file"""
        tokens_dir = os.path.join(os.path.dirname(__file__), "tokens")
        
        if not os.path.exists(tokens_dir):
            messagebox.showwarning(
                "No Tokens Directory", 
                "No tokens directory found.\n\n"
                "Choose 'Generate New Token' instead, or create the tokens directory manually."
            )
            return None
        
        # Get list of existing token files
        try:
            token_files = [f for f in os.listdir(tokens_dir) if f.endswith('.json') and f.startswith('yt_token_')]
            
            if not token_files:
                result = messagebox.askyesno(
                    "No Existing Tokens", 
                    "No existing token files found.\n\n"
                    "Would you like to generate a new token instead?"
                )
                if result:
                    return self.generate_new_token(profile_name)
                return None
            
            # Create selection dialog
            dialog = tk.Toplevel(self.root)
            dialog.title("Select Existing Token")
            dialog.geometry("500x400")
            dialog.configure(bg='#f8f9fa')
            dialog.transient(self.root)
            dialog.grab_set()
            
            # Center the dialog
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
            y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
            dialog.geometry(f"+{x}+{y}")
            
            selected_token = None
            
            # Dialog content
            ttk.Label(dialog, text=f"Select token for: {profile_name}", 
                     font=('Segoe UI', 12, 'bold')).pack(pady=10)
            
            ttk.Label(dialog, text="Available token files:", 
                     font=('Segoe UI', 10)).pack(pady=(0, 5))
            
            # Listbox for token files
            list_frame = ttk.Frame(dialog)
            list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
            
            token_listbox = tk.Listbox(list_frame, font=('Segoe UI', 10), height=10)
            scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=token_listbox.yview)
            token_listbox.configure(yscrollcommand=scrollbar.set)
            
            for token_file in token_files:
                # Extract channel name from filename for display
                display_name = token_file.replace('yt_token_', '').replace('.json', '').replace('_', ' ').title()
                token_listbox.insert(tk.END, f"{display_name} ({token_file})")
            
            token_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Buttons
            btn_frame = ttk.Frame(dialog)
            btn_frame.pack(fill=tk.X, padx=20, pady=10)
            
            def on_select():
                nonlocal selected_token
                selection = token_listbox.curselection()
                if selection:
                    selected_token = token_files[selection[0]]
                    dialog.destroy()
                else:
                    messagebox.showwarning("No Selection", "Please select a token file.")
            
            def on_cancel():
                nonlocal selected_token
                selected_token = None
                dialog.destroy()
            
            def on_generate_new():
                nonlocal selected_token
                dialog.destroy()
                selected_token = self.generate_new_token(profile_name)
            
            ttk.Button(btn_frame, text="✅ Use Selected Token", 
                      command=on_select, style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 10))
            ttk.Button(btn_frame, text="➕ Generate New Token", 
                      command=on_generate_new, style="TButton").pack(side=tk.LEFT, padx=(0, 10))
            ttk.Button(btn_frame, text="❌ Cancel", 
                      command=on_cancel, style="Danger.TButton").pack(side=tk.RIGHT)
            
            # Wait for dialog to close
            dialog.wait_window()
            
            return selected_token
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to list token files: {str(e)}")
            return None
    
    def delete_profile(self):
        """Delete selected profile and all related files"""
        if not self.selected_profile:
            messagebox.showwarning("No Selection", "Please select a profile to delete")
            return
        
        # Check for unsaved changes first
        self.has_unsaved_changes = self.check_for_unsaved_changes()
        if self.has_unsaved_changes:
            result = messagebox.askyesnocancel(
                "Unsaved Changes",
                f"You have unsaved changes to '{self.selected_profile}'.\n\n"
                f"Do you want to save your changes before deleting this profile?\n\n"
                f"• Yes: Save changes first, then delete profile\n"
                f"• No: Delete profile without saving changes\n"
                f"• Cancel: Keep profile and return to editor"
            )
            
            if result is None:  # Cancel
                return
            elif result is True:  # Save first
                try:
                    self.save_profile_from_editor()
                    self.has_unsaved_changes = False
                    self.update_save_indicator()
                except Exception as e:
                    messagebox.showerror("Save Error", f"Failed to save changes: {str(e)}")
                    return
            # If result is False, continue with deletion without saving
            
        if messagebox.askyesno("Delete Profile", 
                              f"Delete profile '{self.selected_profile}' and ALL related files?\n\n"
                              f"This will delete:\n"
                              f"• Profile configuration\n"
                              f"• YouTube token file\n" 
                              f"• Processing history (processed_*.json)\n\n"
                              f"This action cannot be undone!"):
            
            profile = self.profiles.get(self.selected_profile, {})
            profile_label = profile.get('label', self.selected_profile)
            
            # Track what was deleted for logging
            deleted_files = []
            
            # 1. Delete YouTube token file
            yt_token = profile.get('yt_token', '')
            if yt_token:
                token_path = os.path.join(os.path.dirname(__file__), "tokens", yt_token)
                if os.path.exists(token_path):
                    try:
                        os.remove(token_path)
                        deleted_files.append(f"Token: {yt_token}")
                        self.log_message(f"❌ Deleted token file: {yt_token}")
                    except Exception as e:
                        self.log_message(f"⚠️ Could not delete token file {yt_token}: {e}")
            
            # 2. Delete processed history file
            processed_file = os.path.join(os.path.dirname(__file__), "processed", f"processed_{profile_label}.json")
            if os.path.exists(processed_file):
                try:
                    os.remove(processed_file)
                    deleted_files.append(f"History: processed_{profile_label}.json")
                    self.log_message(f"❌ Deleted processing history: processed_{profile_label}.json")
                except Exception as e:
                    self.log_message(f"⚠️ Could not delete processed file: {e}")
            
            # 3. Remove from profiles dict
            profile_name_to_delete = self.selected_profile
            del self.profiles[self.selected_profile]
            deleted_files.append("Profile configuration")
            self.log_message(f"❌ Removed '{profile_name_to_delete}' from profiles dictionary")
            
            # 4. Clear selected profile before saving to avoid conflicts
            self.selected_profile = None
            
            # 5. Save updated profiles.json directly without trying to save current profile
            try:
                profiles_file = os.path.join(os.path.dirname(__file__), "profiles.json")
                with open(profiles_file, 'w', encoding='utf-8') as f:
                    json.dump(self.profiles, f, indent=2, ensure_ascii=False)
                self.log_message(f"💾 Saved updated profiles.json (removed '{profile_name_to_delete}')")
                
                # Update startup batch file
                self.update_startup_batch_file()
                
            except Exception as e:
                self.log_message(f"❌ Error saving profiles after deletion: {str(e)}")
                messagebox.showerror("Save Error", f"Failed to save profiles after deletion: {e}")
                return
            
            # 6. Update UI
            self.refresh_profile_list()
            self.refresh_channel_status()
            
            # 7. Clear editor completely
            if hasattr(self, 'profile_vars'):
                for var in self.profile_vars.values():
                    if hasattr(var, 'set'):
                        if isinstance(var, tk.BooleanVar):
                            var.set(False)
                        else:
                            var.set('')
            
            # Clear listboxes
            if hasattr(self, 'hashtags_listbox'):
                self.hashtags_listbox.delete(0, tk.END)
            if hasattr(self, 'titles_listbox'):
                self.titles_listbox.delete(0, tk.END)
            
            # Reset unsaved changes tracking
            self.has_unsaved_changes = False
            self.original_profile_data = {}
            
            # Update save indicator
            if hasattr(self, 'update_save_indicator'):
                self.update_save_indicator()
            
            # Clear any profile-specific UI elements
            if hasattr(self, 'profile_name_label'):
                self.profile_name_label.config(text="No profile selected")
            
            # Force refresh the entire profile tab display
            if hasattr(self, 'setup_profile_tab'):
                try:
                    # Clear selection in the listbox
                    self.profile_listbox.selection_clear(0, tk.END)
                except:
                    pass
            
            # Show summary
            deleted_summary = '\n• '.join(deleted_files)
            self.log_message(f"❌ Profile '{profile_label}' deleted completely")
            self.log_message(f"📋 Deleted items:\n• {deleted_summary}")
            
            messagebox.showinfo("Profile Deleted", 
                              f"Profile '{profile_label}' and all related files have been deleted:\n\n"
                              f"• {deleted_summary}")
        else:
            self.log_message(f"❌ Profile deletion cancelled by user")
    
    def reload_profiles(self):
        """Reload profiles from file"""
        self.load_profiles()
        self.refresh_profile_list()
        self.refresh_channel_status()
        self.log_message("🔄 Profiles reloaded")
    
    def browse_token_file(self):
        """Browse for YouTube token file"""
        # Set initial directory to tokens folder
        tokens_dir = os.path.join(os.path.dirname(__file__), "tokens")
        if not os.path.exists(tokens_dir):
            os.makedirs(tokens_dir)  # Create tokens folder if it doesn't exist
        
        filename = filedialog.askopenfilename(
            title="Select YouTube Token File",
            initialdir=tokens_dir,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            self.profile_vars['yt_token'].set(os.path.basename(filename))
    
    def browse_music_dir(self):
        """Browse for music directory"""
        dirname = filedialog.askdirectory(title="Select Music Directory")
        if dirname:
            self.profile_vars['music_dir'].set(dirname)
    
    def browse_font_file(self):
        """Browse for font file"""
        filename = filedialog.askopenfilename(
            title="Select Font File",
            filetypes=[("TrueType fonts", "*.ttf"), ("OpenType fonts", "*.otf"), ("All files", "*.*")]
        )
        if filename:
            self.profile_vars['font_path'].set(filename)
    
    def refresh_channel_status(self):
        """Refresh channel status in the processing tab"""
        # Clear existing items
        for item in self.channels_tree.get_children():
            self.channels_tree.delete(item)
        
        # Check if client_secrets.json is missing
        missing_secrets = not self.check_client_secrets_exists()
        
        # Add channels
        for profile_name, profile in self.profiles.items():
            # Check for last processed date
            processed_file = os.path.join(os.path.dirname(__file__), "processed", f"processed_{profile['label']}.json")
            last_processed = "Never"
            status = "Setup Required" if missing_secrets else "Ready"
            
            if os.path.exists(processed_file) and not missing_secrets:
                try:
                    with open(processed_file, 'r') as f:
                        data = json.load(f)
                    if data:
                        # Get the most recent upload
                        last_upload = max(data, key=lambda x: x.get('upload_date', x.get('date', '')))
                        upload_date = last_upload.get('upload_date', last_upload.get('date', 'Unknown'))
                        
                        # Check if uploaded today using the more precise upload_date
                        from datetime import date
                        today = date.today().isoformat()  # Format: YYYY-MM-DD
                        
                        if upload_date.startswith(today):
                            last_processed = f"Today ({upload_date[11:16] if len(upload_date) > 16 else 'completed'})"
                            status = "Completed Today"
                        else:
                            # Show just the date part for older uploads
                            last_processed = upload_date[:10] if len(upload_date) >= 10 else upload_date
                            status = "Ready"
                except:
                    pass
            
            self.channels_tree.insert('', tk.END, values=(
                profile['label'],
                f"r/{profile['subreddit']}",
                "✅ Yes" if profile.get('run_on_startup', False) else "❌ No",
                last_processed,
                status
            ))
        
        # Update button states after refreshing
        if hasattr(self, 'process_selected_button'):
            self.on_channel_selection_change(None)
    
    def on_channel_selection_change(self, event):
        """Handle channel selection changes to update button text"""
        # Check if buttons exist (they might not during initialization)
        if not hasattr(self, 'process_selected_button') or not hasattr(self, 'test_selected_button'):
            return
            
        selection = self.channels_tree.selection()
        count = len(selection)
        
        if count == 0:
            # No selection
            self.process_selected_button.config(text="▶️ Process Selected Channel", state='disabled')
            self.test_selected_button.config(text="🧪 Test Selected Channel", state='disabled')
        elif count == 1:
            # Single selection
            self.process_selected_button.config(text="▶️ Process Selected Channel", state='normal')
            self.test_selected_button.config(text="🧪 Test Selected Channel", state='normal')
        else:
            # Multiple selection
            self.process_selected_button.config(text=f"▶️ Process Selected Channels ({count})", state='normal')
            self.test_selected_button.config(text=f"🧪 Test Selected Channels ({count})", state='normal')
    
    def process_selected_channel(self):
        """Process the selected channel(s)"""
        selection = self.channels_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select one or more channels to process")
            return
        
        if len(selection) == 1:
            # Single channel - use existing logic
            item = self.channels_tree.item(selection[0])
            channel_label = item['values'][0]
            self.run_channel_processing(channel_label, test_mode=False)
        else:
            # Multiple channels - use bulk processing logic with selected channels
            channel_labels = []
            for sel in selection:
                item = self.channels_tree.item(sel)
                channel_labels.append(item['values'][0])
            
            if messagebox.askyesno("Process Multiple Channels", 
                                 f"Process {len(channel_labels)} selected channels?\n\n"
                                 f"Channels: {', '.join(channel_labels)}\n\n"
                                 f"This may take a long time."):
                self.run_selected_channels_processing(channel_labels, test_mode=False)
    
    def test_selected_channel(self):
        """Test process the selected channel(s)"""
        selection = self.channels_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select one or more channels to test")
            return
        
        if len(selection) == 1:
            # Single channel - use existing logic
            item = self.channels_tree.item(selection[0])
            channel_label = item['values'][0]
            self.run_channel_processing(channel_label, test_mode=True)
        else:
            # Multiple channels - use bulk processing logic with selected channels
            channel_labels = []
            for sel in selection:
                item = self.channels_tree.item(sel)
                channel_labels.append(item['values'][0])
            
            if messagebox.askyesno("Test Multiple Channels", 
                                 f"Test process {len(channel_labels)} selected channels?\n\n"
                                 f"Channels: {', '.join(channel_labels)}"):
                self.run_selected_channels_processing(channel_labels, test_mode=True)
    
    def process_all_channels(self):
        """Process all channels"""
        if not self.profiles:
            messagebox.showwarning("No Profiles", "No channel profiles found")
            return
        
        if messagebox.askyesno("Process All", "Process all channels? This may take a long time."):
            self.run_bulk_processing(test_mode=False)
    
    def test_all_channels(self):
        """Test process all channels"""
        if not self.profiles:
            messagebox.showwarning("No Profiles", "No channel profiles found")
            return
        
        if messagebox.askyesno("Test All", "Test process all channels?"):
            self.run_bulk_processing(test_mode=True)
    
    def channel_processed_today(self, channel_label):
        """Check if a channel has been successfully processed today"""
        try:
            from datetime import datetime, date
            
            processed_file = os.path.join(os.path.dirname(__file__), "processed", f"processed_{channel_label}.json")
            
            if not os.path.exists(processed_file):
                return False
            
            # Load the processed uploads
            with open(processed_file, 'r', encoding='utf-8') as f:
                uploads = json.load(f)
            
            if not uploads:
                return False
            
            # Get today's date
            today = date.today().isoformat()  # Format: YYYY-MM-DD
            
            # Check if there's any upload from today
            for upload in uploads:
                upload_date = upload.get('upload_date', '')
                # Check if the upload date starts with today's date (handles full datetime strings)
                if upload_date.startswith(today):
                    return True
            
            return False
            
        except Exception as e:
            # If there's any error reading the file, assume not processed today
            self.log_message(f"🔍 Debug: Error checking if channel processed today: {str(e)}")
            return False

    def channel_daily_limit_reached(self, channel_label):
        """Check if a channel has reached its daily upload limit"""
        try:
            from datetime import datetime, date
            
            # Find the profile for this channel to get the daily limit
            daily_limit = 1  # Default
            for prof_name, prof_data in self.profiles.items():
                if prof_data['label'] == channel_label:
                    daily_limit = prof_data.get('daily_upload_limit', 1)
                    break
            
            processed_file = os.path.join(os.path.dirname(__file__), "processed", f"processed_{channel_label}.json")
            
            if not os.path.exists(processed_file):
                return False
            
            # Load the processed uploads
            with open(processed_file, 'r', encoding='utf-8') as f:
                uploads = json.load(f)
            
            if not uploads:
                return False
            
            # Get today's date in the same format used in uploads (YYYY-MM-DD)
            today = date.today().isoformat()  # Format: YYYY-MM-DD
            
            # Count uploads from today - check the 'date' field (not 'upload_date')
            today_upload_count = 0
            for upload in uploads:
                upload_date = upload.get('date', '')  # Changed from 'upload_date' to 'date'
                # Direct comparison since both are in YYYY-MM-DD format
                if upload_date == today:
                    today_upload_count += 1
            
            # Debug logging
            self.log_message(f"🔍 Debug: Channel '{channel_label}' - {today_upload_count}/{daily_limit} uploads today ({today})")
            
            return today_upload_count >= daily_limit
            
        except Exception as e:
            # If there's any error reading the file, assume limit not reached
            self.log_message(f"🔍 Debug: Error checking daily upload limit: {str(e)}")
            return False

    def run_channel_processing(self, channel_label, test_mode=False):
        """Run processing for a specific channel"""
        # Debug logging
        self.log_message(f"🔍 Debug: Starting channel processing for '{channel_label}' (test_mode={test_mode})")
        
        # Check for client_secrets.json first
        if not self.check_client_secrets_exists():
            messagebox.showerror(
                "Missing client_secrets.json", 
                "Cannot process videos without client_secrets.json file.\n\n"
                "Please click the ' Setup Guide' button in the warning banner to get instructions."
            )
            return
        
        # Check if channel has reached its daily upload limit (unless in test mode)
        if not test_mode:
            self.log_message(f"🔍 Debug: Checking daily upload limit for '{channel_label}'...")
            if self.channel_daily_limit_reached(channel_label):
                # Find the profile to get the daily limit for the message
                daily_limit = 1
                for prof_name, prof_data in self.profiles.items():
                    if prof_data['label'] == channel_label:
                        daily_limit = prof_data.get('daily_upload_limit', 1)
                        break
                
                mode_emoji = "⏰"
                self.log_message(f"{mode_emoji} Channel '{channel_label}' has reached its daily upload limit!")
                self.log_message(f"📅 Daily limit: {daily_limit} video(s) per day. Processing skipped to avoid exceeding quota.")
                self.log_message(f"💡 Use 'Test Mode' if you want to test the channel without uploading.")
                messagebox.showinfo(
                    "Daily Upload Limit Reached", 
                    f"Channel '{channel_label}' has reached its daily upload limit of {daily_limit} video(s).\n\n"
                    f"Processing has been skipped to avoid exceeding your configured quota.\n\n"
                    f"Use 'Test Selected Channel' if you want to test without uploading, or "
                    f"increase the daily limit in the channel profile settings."
                )
                return
            else:
                self.log_message(f"✅ Debug: Daily upload limit check passed for '{channel_label}'")
        else:
            self.log_message(f"🧪 Debug: Test mode - skipping daily upload limit check")

        if self.is_processing:
            messagebox.showwarning("Processing", "Already processing. Please wait.")
            return
        
        # Save current profile if editing
        if self.selected_profile:
            self.save_profile_from_editor()
            self.save_profiles()
        
        mode_text = "Test" if test_mode else "Production"
        process_name = f"{channel_label} ({mode_text} mode)"
        self.start_processing_mode(process_name)
        self.status_label.config(text=f"Processing {process_name}...")
        self.progress_var.set(0)  # Start at 0%
        
        # Auto-switch to logs tab when processing starts
        self.notebook.select(3)  # Index 3 is the logs tab
        
        def process_thread():
            import io
            import contextlib
            import sys
            
            try:
                # Check for abort before starting
                if self.abort_processing:
                    self.end_processing_mode(False, "Process aborted before starting")
                    return
                
                # Find the profile for this channel
                profile = None
                for prof_name, prof_data in self.profiles.items():
                    if prof_data['label'] == channel_label:
                        profile = prof_data
                        break
                
                if not profile:
                    self.processing_queue.put(("error", f"Profile not found for {channel_label}"))
                    return
                
                mode_emoji = "🧪" if test_mode else "🚀"
                self.processing_queue.put(("log", f"{mode_emoji} Starting {mode_text.lower()} processing for {channel_label}"))
                
                # Track the current processing channel
                self.current_processing_channel = channel_label
                
                self.processing_queue.put(("log", f"📂 Subreddit: r/{profile.get('subreddit', 'unknown')}"))
                self.processing_queue.put(("log", f"🎵 Music: {profile.get('music_dir', 'default')}"))
                
                # Add video selection information
                video_selection = profile.get('video_selection', {})
                video_sort_method = video_selection.get('sort_method', 'top_month')
                enable_fallback = video_selection.get('enable_fallback', True)
                
                # Convert sort method to display name
                sort_display_names = {
                    'hot': '🔥 Hot (Reddit\'s trending algorithm)',
                    'top_all': '⭐ Top - All Time',
                    'top_year': '🏆 Top - This Year',
                    'top_month': '📆 Top - This Month',
                    'new': '📰 Newest'
                }
                sort_display = sort_display_names.get(video_sort_method, f"🎯 {video_sort_method}")
                fallback_status = "✅ Enabled" if enable_fallback else "❌ Disabled"
                
                self.processing_queue.put(("log", f"🎯 Video Selection: {sort_display}"))
                self.processing_queue.put(("log", f"🔄 Fallback Mode: {fallback_status}"))
                self.processing_queue.put(("log", f" 📊 Daily Upload Limit: {profile.get('daily_upload_limit', 1)} video(s)"))
                
                self.processing_queue.put(("progress", 10))
                
                if test_mode:
                    self.processing_queue.put(("log", f"🔒 Test mode: Videos will be uploaded as PRIVATE and won't count towards daily limits"))
                    # Create a copy of the profile with test mode settings
                    test_profile = profile.copy()
                    test_profile['test_mode'] = True
                    profile = test_profile
                
                # Create a progress callback function
                announced_stages = set()  # Track which stages we've already announced
                
                def progress_callback(stage, progress):
                    # Check for abort during processing
                    if self.abort_processing:
                        raise Exception("Process aborted by user")
                    
                    # Handle special daily limit reached case
                    if stage == "daily_limit_reached":
                        # Find the profile to get the daily limit for the message
                        daily_limit = 1
                        for prof_name, prof_data in self.profiles.items():
                            if prof_data['label'] == channel_label:
                                daily_limit = prof_data.get('daily_upload_limit', 1)
                                break
                        
                        self.processing_queue.put(("log", f"⏰ Daily upload limit reached ({daily_limit} videos/day)"))
                        self.processing_queue.put(("log", f"📅 Processing skipped to avoid exceeding quota"))
                        self.processing_queue.put(("log", f"💡 Use 'Test Mode' to test without uploading"))
                        
                        # Show as a "successful skip" rather than error
                        self.processing_queue.put(("success", f"⏰ {channel_label} skipped - daily limit reached ({daily_limit}/day)"))
                        return
                        
                    stage_emojis = {
                        "fetching": "🔍",
                        "processing": "🎬", 
                        "rendering": "🎨",
                        "uploading": "🚀",
                        "cleanup": "🧹"
                    }
                    emoji = stage_emojis.get(stage, "⚙️")
                    
                    # Only show the stage message once when it starts
                    if stage not in announced_stages:
                        self.processing_queue.put(("log", f"{emoji} {stage.title()}..."))
                        self.processing_queue.put(("start_animation", stage))
                        announced_stages.add(stage)
                    
                    # Stop animation when stage completes (progress reaches 100 for that stage)
                    if progress >= 100:
                        self.processing_queue.put(("stop_animation", stage))
                    
                    self.processing_queue.put(("progress", progress))
                
                # Create an abort check callback function
                def abort_check_callback():
                    return self.abort_processing
                
                # Add the callbacks to the profile
                profile['_gui_progress_callback'] = progress_callback
                profile['_gui_abort_callback'] = abort_check_callback
                profile['_gui_mode'] = True  # Flag to indicate GUI mode
                
                # Check for abort before starting main processing
                if self.abort_processing:
                    raise Exception("Process aborted by user")
                
                # Run the processing (don't capture stdout in GUI mode)
                try:
                    pv = load_process_videos()
                    pv.process_channel_with_utf8_recovery(profile)
                except UnicodeDecodeError as ude:
                    raise Exception(f"UTF-8 encoding error: {str(ude)}. This usually happens with special characters in Reddit posts or video content. Try processing a different subreddit or check for special characters in your profile settings.")
                except UnicodeEncodeError as uee:
                    raise Exception(f"UTF-8 encoding error: {str(uee)}. This usually happens when trying to save content with special characters. Check your channel name and settings for special characters.")
                
                # Check for abort after processing
                if self.abort_processing:
                    raise Exception("Process aborted by user")
                
                self.processing_queue.put(("progress", 100))
                success_emoji = "✅" if not test_mode else "🧪✅"
                self.processing_queue.put(("success", f"{success_emoji} {channel_label} processed successfully"))
                
            except Exception as e:
                error_emoji = "❌" if not test_mode else "🧪❌"
                error_msg = str(e)
                
                # Handle user abort differently
                if "Process aborted by user" in error_msg or self.abort_processing:
                    self.processing_queue.put(("abort", f"🛑 Process aborted by user"))
                    return
                
                # Extract more details from specific error types
                if "HttpError" in error_msg:
                    if "uploadLimitExceeded" in error_msg or "exceeded the number of videos" in error_msg:
                        error_msg = f"Upload limit exceeded - Daily quota reached for this channel"
                    elif "quotaExceeded" in error_msg:
                        error_msg = f"API quota exceeded - Try again later"
                    elif "400" in error_msg and "exceeded" in error_msg:
                        error_msg = f"Upload limit exceeded - Daily quota reached"
                    else:
                        error_msg = f"YouTube API error: {error_msg}"
                elif "Upload failed" in error_msg:
                    error_msg = f"Upload failed: {error_msg}"
                
                self.processing_queue.put(("error", f"{error_emoji} Error processing {channel_label}: {error_msg}"))
            finally:
                self.processing_queue.put(("finished", ""))
        
        thread = threading.Thread(target=process_thread, daemon=True)
        thread.start()
    
    def run_selected_channels_processing(self, channel_labels, test_mode=False):
        """Run processing for selected channels with detailed output like single channel processing"""
        # Check for client_secrets.json first
        if not self.check_client_secrets_exists():
            messagebox.showerror(
                "Missing client_secrets.json", 
                "Cannot process videos without client_secrets.json file.\n\n"
                "Please click the ' Setup Guide' button in the warning banner to get instructions."
            )
            return
        
        if self.is_processing:
            messagebox.showwarning("Processing", "Already processing. Please wait.")
            return
        
        # Save current profile if editing
        if self.selected_profile:
            self.save_profile_from_editor()
            self.save_profiles()
        
        mode_text = "Test" if test_mode else "Production"
        process_name = f"Processing {len(channel_labels)} selected channels ({mode_text} mode)"
        self.start_processing_mode(process_name)
        self.status_label.config(text=f"Processing selected channels ({mode_text} mode)...")
        
        # Auto-switch to logs tab when processing starts
        self.notebook.select(3)  # Index 3 is the logs tab
        
        def process_thread():
            try:
                # Check for abort before starting
                if self.abort_processing:
                    self.processing_queue.put(("abort", f"🛑 Selected channels process aborted before starting"))
                    return
                
                total_channels = len(channel_labels)
                mode_emoji = "🧪" if test_mode else "🚀"
                self.processing_queue.put(("log", f"{mode_emoji} Starting {mode_text.lower()} processing for {total_channels} selected channel(s)"))
                self.processing_queue.put(("log", f"📋 Selected channels: {', '.join(channel_labels)}"))
                
                if test_mode:
                    self.processing_queue.put(("log", f"🔒 Test mode: All videos will be uploaded as PRIVATE"))
                
                successful_channels = 0
                failed_channels = 0
                
                for i, channel_label in enumerate(channel_labels):
                    # Check for abort at the start of each channel
                    if self.abort_processing:
                        self.processing_queue.put(("abort", f"🛑 Selected channels process aborted after {i} channels"))
                        return
                    
                    # Find the profile for this channel
                    profile = None
                    for prof_name, prof_data in self.profiles.items():
                        if prof_data['label'] == channel_label:
                            profile = prof_data
                            break
                    
                    if not profile:
                        self.processing_queue.put(("error", f"❌ Profile not found for {channel_label}"))
                        failed_channels += 1
                        continue
                    
                    # Check if channel has reached its daily upload limit (unless in test mode)
                    if not test_mode and self.channel_daily_limit_reached(channel_label):
                        daily_limit = profile.get('daily_upload_limit', 1)
                        self.processing_queue.put(("log", f"⏰ Channel '{channel_label}' has reached daily limit ({daily_limit} videos) - skipping"))
                        continue
                    
                    # Update progress
                    progress = (i / total_channels) * 100
                    self.processing_queue.put(("progress", progress))
                    
                    # Channel separator and detailed info (same as single channel processing)
                    self.processing_queue.put(("log", f"📍 Processing channel {i+1}/{total_channels}: {channel_label}"))
                    self.processing_queue.put(("log", f"📂 Subreddit: r/{profile.get('subreddit', 'unknown')}"))
                    self.processing_queue.put(("log", f"🎵 Music: {profile.get('music_dir', 'default')}"))
                    
                    # Add video selection information
                    video_selection = profile.get('video_selection', {})
                    video_sort_method = video_selection.get('sort_method', 'top_month')
                    enable_fallback = video_selection.get('enable_fallback', True)
                    
                    # Convert sort method to display name
                    sort_display_names = {
                        'hot': '🔥 Hot (Reddit\'s trending algorithm)',
                        'top_all': '⭐ Top - All Time',
                        'top_year': '🏆 Top - This Year',
                        'top_month': '📆 Top - This Month',
                        'new': '📰 Newest'
                    }
                    sort_display = sort_display_names.get(video_sort_method, f"🎯 {video_sort_method}")
                    fallback_status = "✅ Enabled" if enable_fallback else "❌ Disabled"
                    
                    self.processing_queue.put(("log", f"🎯 Video Selection: {sort_display}"))
                    self.processing_queue.put(("log", f"🔄 Fallback Mode: {fallback_status}"))
                    
                    if test_mode:
                        # Create a copy of the profile with test mode settings
                        test_profile = profile.copy()
                        test_profile['test_mode'] = True
                        profile = test_profile
                    
                    # Track the current processing channel
                    self.current_processing_channel = channel_label
                    
                    # Create progress callback for detailed stage logging (same as single channel)
                    announced_stages = set()
                    
                    def progress_callback(stage, progress_pct):
                        if self.abort_processing:
                            raise Exception("Process aborted by user")
                            
                        stage_emojis = {
                            "fetching": "🔍",
                            "processing": "🎬", 
                            "rendering": "⚙️",
                            "uploading": "🚀",
                            "cleanup": "🧹"
                        }
                        emoji = stage_emojis.get(stage, "⚙️")
                        
                        # Only show the stage message once when it starts
                        if stage not in announced_stages:
                            self.processing_queue.put(("log", f"  {emoji} {stage.title()}..."))
                            self.processing_queue.put(("start_animation", stage))
                            announced_stages.add(stage)
                        
                        # Stop animation when stage completes
                        if progress_pct >= 100:
                            self.processing_queue.put(("stop_animation", stage))
                    
                    # Create abort check callback
                    def abort_check_callback():
                        return self.abort_processing
                    
                    # Add the callbacks to the profile
                    profile['_gui_progress_callback'] = progress_callback
                    profile['_gui_abort_callback'] = abort_check_callback
                    profile['_gui_mode'] = True
                    
                    try:
                        # Process this channel with detailed output
                        pv = load_process_videos()
                        pv.process_channel_with_utf8_recovery(profile)
                        successful_channels += 1
                        success_emoji = "✅" if not test_mode else "🧪✅"
                        self.processing_queue.put(("log", f"  {success_emoji} {channel_label} completed successfully"))
                        
                    except Exception as e:
                        failed_channels += 1
                        error_emoji = "❌" if not test_mode else "🧪❌"
                        error_msg = str(e)
                        
                        # Handle user abort differently
                        if "Process aborted by user" in error_msg or self.abort_processing:
                            self.processing_queue.put(("abort", f"🛑 Process aborted by user"))
                            return
                        
                        # Extract more details from specific error types
                        if "HttpError" in error_msg:
                            if "uploadLimitExceeded" in error_msg or "exceeded the number of videos" in error_msg:
                                error_msg = f"Upload limit exceeded - Daily quota reached"
                            elif "quotaExceeded" in error_msg:
                                error_msg = f"API quota exceeded - Try again later"
                            elif "400" in error_msg and "exceeded" in error_msg:
                                error_msg = f"Upload limit exceeded - Daily quota reached"
                            else:
                                error_msg = f"YouTube API error: {error_msg}"
                        elif "Upload failed" in error_msg:
                            error_msg = f"Upload failed: {error_msg}"
                        
                        self.processing_queue.put(("log", f"  {error_emoji} {channel_label} failed: {error_msg}"))
                
                # Final summary
                self.processing_queue.put(("progress", 100))
                summary_emoji = "🎉" if not test_mode else "🧪🎉"
                self.processing_queue.put(("success", f"{summary_emoji} Selected channels processing completed: {successful_channels} successful, {failed_channels} failed"))
                
            except Exception as e:
                error_emoji = "❌" if not test_mode else "🧪❌"
                error_msg = str(e)
                
                if "Process aborted by user" in error_msg or self.abort_processing:
                    self.processing_queue.put(("abort", f"🛑 Process aborted by user"))
                    return
                
                self.processing_queue.put(("error", f"{error_emoji} Error in selected channels processing: {error_msg}"))
            finally:
                self.processing_queue.put(("finished", ""))
        
        thread = threading.Thread(target=process_thread, daemon=True)
        thread.start()
    
    def run_bulk_processing(self, test_mode=False):
        """Run processing for all channels"""
        # Check for client_secrets.json first
        if not self.check_client_secrets_exists():
            messagebox.showerror(
                "Missing client_secrets.json", 
                "Cannot process videos without client_secrets.json file.\n\n"
                "Please click the ' Setup Guide' button in the warning banner to get instructions."
            )
            return
        
        if self.is_processing:
            messagebox.showwarning("Processing", "Already processing. Please wait.")
            return
        
        # Save current profile if editing
        if self.selected_profile:
            self.save_profile_from_editor()
            self.save_profiles()
        
        mode_text = "Test" if test_mode else "Production"
        process_name = f"Bulk processing all channels ({mode_text} mode)"
        self.start_processing_mode(process_name)
        self.status_label.config(text=f"Bulk processing all channels ({mode_text} mode)...")
        
        # Auto-switch to logs tab when processing starts
        self.notebook.select(3)  # Index 3 is the logs tab
        
        def process_thread():
            try:
                # Check for abort before starting
                if self.abort_processing:
                    self.processing_queue.put(("abort", f"🛑 Bulk process aborted before starting"))
                    return
                
                total_channels = len(self.profiles)
                mode_emoji = "🧪" if test_mode else "🚀"
                self.processing_queue.put(("log", f"{mode_emoji} Starting bulk {mode_text.lower()} processing for {total_channels} channel(s)"))
                
                if test_mode:
                    self.processing_queue.put(("log", f"🔒 Test mode: All videos will be uploaded as PRIVATE"))
                
                for i, (profile_name, profile) in enumerate(self.profiles.items()):
                    # Check for abort at the start of each channel
                    if self.abort_processing:
                        self.processing_queue.put(("abort", f"🛑 Bulk process aborted after {i} channels"))
                        return
                    
                    progress = (i / total_channels) * 100
                    self.processing_queue.put(("progress", progress))
                    self.processing_queue.put(("log", f"📍 Processing channel {i+1}/{total_channels}: {profile['label']}"))
                    self.processing_queue.put(("log", f"  └─ Subreddit: r/{profile.get('subreddit', 'unknown')}"))
                    self.processing_queue.put(("log", f"  └─ Music: {profile.get('music_dir', 'default')}"))
                    
                    # Add video selection information for bulk processing
                    video_selection = profile.get('video_selection', {})
                    video_sort_method = video_selection.get('sort_method', 'top_month')
                    enable_fallback = video_selection.get('enable_fallback', True)
                    
                    # Convert sort method to display name
                    sort_display_names = {
                        'hot': '🔥 Hot',
                        'top_all': '⭐ Top - All Time',
                        'top_year': '🏆 Top - This Year',
                        'top_month': '📆 Top - This Month',
                        'new': '📰 Newest'
                    }
                    sort_display = sort_display_names.get(video_sort_method, f"🎯 {video_sort_method}")
                    fallback_status = "✅ Enabled" if enable_fallback else "❌ Disabled"
                    
                    self.processing_queue.put(("log", f"  └─ Video Selection: {sort_display}"))
                    self.processing_queue.put(("log", f"  └─ Fallback: {fallback_status}"))
                    
                    # Check if channel has reached its daily upload limit (unless in test mode)
                    if not test_mode and self.channel_daily_limit_reached(profile['label']):
                        daily_limit = profile.get('daily_upload_limit', 1)
                        self.processing_queue.put(("log", f"  └─ ⏰ Daily limit reached ({daily_limit} videos) - skipping"))
                        continue
                    
                    try:
                        # Check for abort before processing each channel
                        if self.abort_processing:
                            self.processing_queue.put(("abort", f"🛑 Bulk process aborted during {profile['label']}"))
                            return
                        
                        # Track the current processing channel
                        self.current_processing_channel = profile['label']
                        
                        # Create progress callback for detailed stage logging (same as single channel)
                        announced_stages = set()
                        
                        def progress_callback(stage, progress_pct):
                            if self.abort_processing:
                                raise Exception("Process aborted by user")
                                
                            stage_emojis = {
                                "fetching": "🔍",
                                "processing": "🎬", 
                                "rendering": "⚙️",
                                "uploading": "🚀",
                                "cleanup": "🧹"
                            }
                            emoji = stage_emojis.get(stage, "⚙️")
                            
                            # Only show the stage message once when it starts
                            if stage not in announced_stages:
                                self.processing_queue.put(("log", f"  {emoji} {stage.title()}..."))
                                self.processing_queue.put(("start_animation", stage))
                                announced_stages.add(stage)
                            
                            # Stop animation when stage completes
                            if progress_pct >= 100:
                                self.processing_queue.put(("stop_animation", stage))
                        
                        # Create an abort check callback function
                        def abort_check_callback():
                            return self.abort_processing
                        
                        if test_mode:
                            # Create a copy of the profile with test mode settings
                            test_profile = profile.copy()
                            test_profile['test_mode'] = True
                            test_profile['_gui_abort_callback'] = abort_check_callback
                            test_profile['_gui_progress_callback'] = progress_callback
                            test_profile['_gui_mode'] = True
                            try:
                                pv = load_process_videos()
                                pv.process_channel_with_utf8_recovery(test_profile)
                            except (UnicodeDecodeError, UnicodeEncodeError) as ue:
                                raise Exception(f"UTF-8 encoding error in '{profile['label']}': {str(ue)}")
                        else:
                            # Add callbacks to the profile
                            profile_copy = profile.copy()
                            profile_copy['_gui_abort_callback'] = abort_check_callback
                            profile_copy['_gui_progress_callback'] = progress_callback
                            profile_copy['_gui_mode'] = True
                            try:
                                pv = load_process_videos()
                                pv.process_channel_with_utf8_recovery(profile_copy)
                            except (UnicodeDecodeError, UnicodeEncodeError) as ue:
                                raise Exception(f"UTF-8 encoding error in '{profile['label']}': {str(ue)}")
                        
                        success_emoji = "✅" if not test_mode else "🧪✅"
                        self.processing_queue.put(("log", f"  └─ {success_emoji} {profile['label']} completed"))
                    except Exception as e:
                        error_emoji = "❌" if not test_mode else "🧪❌"
                        error_msg = str(e)
                        
                        # Handle user abort
                        if "Process aborted by user" in error_msg or self.abort_processing:
                            self.processing_queue.put(("abort", f"🛑 Bulk process aborted during {profile['label']}"))
                            return
                        
                        # Extract more details from specific error types
                        if "HttpError" in error_msg:
                            if "uploadLimitExceeded" in error_msg or "exceeded the number of videos" in error_msg:
                                error_msg = "Upload limit exceeded - Daily quota reached"
                            elif "quotaExceeded" in error_msg:
                                error_msg = "API quota exceeded - Try again later"
                            elif "400" in error_msg and "exceeded" in error_msg:
                                error_msg = "Upload limit exceeded - Daily quota reached"
                        
                        self.processing_queue.put(("log", f"  └─ {error_emoji} {profile['label']} failed: {error_msg}"))
                
                # Final check for abort
                if self.abort_processing:
                    self.processing_queue.put(("abort", f"🛑 Bulk process aborted at completion"))
                    return
                
                self.processing_queue.put(("progress", 100))
                completion_emoji = "🎉" if not test_mode else "🧪🎉"
                self.processing_queue.put(("success", f"{completion_emoji} Bulk processing completed!"))
                
            except Exception as e:
                error_emoji = "❌" if not test_mode else "🧪❌"
                # Handle user abort
                if "Process aborted by user" in str(e) or self.abort_processing:
                    self.processing_queue.put(("abort", f"🛑 Bulk process aborted"))
                    return
                
                self.processing_queue.put(("error", f"{error_emoji} Bulk processing error: {str(e)}"))
            finally:
                self.processing_queue.put(("finished", ""))
        
        thread = threading.Thread(target=process_thread, daemon=True)
        thread.start()
    
    def manual_run_startup(self):
        """Manually run startup profiles"""
        # Check for client_secrets.json first
        if not self.check_client_secrets_exists():
            messagebox.showerror(
                "Missing client_secrets.json", 
                "Cannot process videos without client_secrets.json file.\n\n"
                "Please click the ' Setup Guide' button in the warning banner to get instructions."
            )
            return
        
        startup_profiles = [name for name, profile in self.profiles.items() if profile.get('run_on_startup', False)]
        
        if not startup_profiles:
            messagebox.showinfo("No Startup Profiles", "No profiles are currently enabled for startup.")
            return
        
        # Calculate total uploads
        total_uploads = sum(self.profiles[name].get('daily_upload_limit', 1) for name in startup_profiles)
        upload_details = []
        for name in startup_profiles:
            limit = self.profiles[name].get('daily_upload_limit', 1)
            upload_details.append(f"• {name} ({limit} upload{'s' if limit != 1 else ''})")
        
        response = messagebox.askyesno(
            "Run Startup Profiles", 
            f"Run {len(startup_profiles)} startup-enabled channel(s) with {total_uploads} total uploads:\n\n" + 
            "\n".join(upload_details)
        )
        if response:
            self.run_startup_profiles(startup_profiles)
    
    def show_startup_profiles(self):
        """Show list of startup-enabled profiles"""
        startup_profiles = [name for name, profile in self.profiles.items() if profile.get('run_on_startup', False)]
        
        if not startup_profiles:
            messagebox.showinfo("Startup Profiles", "No profiles are currently enabled for startup.\n\nTo enable a profile for startup, edit the profile and check 'Run on Startup'.")
        else:
            total_uploads = sum(self.profiles[name].get('daily_upload_limit', 1) for name in startup_profiles)
            profile_details = []
            for name in startup_profiles:
                limit = self.profiles[name].get('daily_upload_limit', 1)
                profile_details.append(f"• {name} ({limit} upload{'s' if limit != 1 else ''})")
            
            profile_list = "\n".join(profile_details)
            messagebox.showinfo("Startup Profiles", f"Profiles enabled for startup ({total_uploads} total uploads):\n\n{profile_list}")
    
    def setup_windows_startup(self):
        """Create or update the startup batch file for automatic startup"""
        startup_profiles = [name for name, profile in self.profiles.items() if profile.get('run_on_startup', False)]
        
        if not startup_profiles:
            messagebox.showwarning("No Startup Profiles", "No profiles are currently enabled for startup.\n\nPlease enable 'Run on Startup' for at least one profile first.")
            return
        
        try:
            # Use the existing update method
            self.update_startup_batch_file()
            
            # Get the batch file path for display
            startup_folder = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
            batch_file_path = os.path.join(startup_folder, 'YouTubeShortsBot.bat')
            
            self.log_message("✅ Windows startup batch file created/updated successfully")
            
            # Show success message
            messagebox.showinfo("Startup Setup Complete", 
                              f"✅ Windows startup has been configured!\n\n"
                              f"Batch file location: {batch_file_path}\n\n"
                              f"Enabled channels ({len(startup_profiles)}):\n" + 
                              "\n".join([f"• {name}" for name in startup_profiles]) + 
                              f"\n\nThese channels will now run automatically when Windows starts.\n\n"
                              f"Note: The batch file will automatically update when you change startup settings and save.")
            
            # Refresh the status display
            self.check_windows_task_status()
            
        except Exception as e:
            self.log_message(f"❌ Error creating startup batch file: {str(e)}")
            messagebox.showerror("Setup Error", f"Failed to create startup batch file:\n\n{str(e)}\n\nTry running as Administrator if permission denied.")
    
    def copy_to_clipboard(self, text):
        """Copy text to clipboard"""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.log_message(f"📋 Copied to clipboard: {text}")
    
    def process_queue(self):
        """Process messages from the processing queue"""
        try:
            while True:
                msg_type, msg_data = self.processing_queue.get_nowait()
                
                if msg_type == "log":
                    self.log_message(msg_data)
                elif msg_type == "error":
                    self.log_message(msg_data)
                    # Don't show popup for individual channel failures in bulk processing
                    if "bulk processing error" in msg_data.lower() or not any(word in msg_data.lower() for word in ["channel", "startup", "processing"]):
                        messagebox.showerror("Processing Error", msg_data)
                elif msg_type == "success":
                    self.log_message(msg_data)
                elif msg_type == "abort":
                    self.log_message(msg_data)
                    self.end_processing_mode(False)
                elif msg_type == "progress":
                    self.progress_var.set(msg_data)
                elif msg_type == "finished":
                    # Only end processing if not already aborted
                    if not self.abort_processing:
                        self.end_processing_mode(True, "Process completed successfully")
                    else:
                        self.end_processing_mode(False, "Process was aborted")
                    self.refresh_channel_status()
                elif msg_type == "start_animation":
                    self.start_period_animation(msg_data)
                elif msg_type == "stop_animation":
                    self.stop_period_animation(msg_data)
                    
        except queue.Empty:
            pass
        
        # Schedule next check - more frequent during processing for faster abort response
        interval = 50 if self.is_processing else 100  # 50ms during processing, 100ms when idle
        self.root.after(interval, self.process_queue)
    
    def log_message(self, message):
        """Add message to log with enhanced formatting and better separation"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Add different formatting based on message type
        # Check for progress stage updates FIRST (before checking for 🚀 start messages)
        if any(emoji in message for emoji in ["🔍", "🎬", " ", "🚀", "🧹"]) and any(word in message for word in ["Fetching", "Processing", "Rendering", "Uploading", "Cleanup"]):
            # Progress stage updates - clean, no separators, consistent spacing for alignment
            formatted_msg = f"[{timestamp}]   {message}\n"
        elif any(msg in message for msg in ["📂 Subreddit:", "🎵 Music:", "🎯 Video Selection:", "🔄 Fallback Mode:", "🔒 Test mode:"]):
            # Configuration details - clean, no separators
            formatted_msg = f"[{timestamp}]   {message}\n"
        elif message.startswith("🚀") or message.startswith("🧪🚀"):
            # Processing start messages - major section
            if "bulk" in message.lower():
                formatted_msg = f"\n{'═' * 80}\n[{timestamp}] {message}\n{'═' * 80}\n"
            else:
                formatted_msg = f"\n{'━' * 60}\n[{timestamp}] {message}\n{'━' * 60}\n"
        elif ("processed successfully" in message or "completed successfully" in message) and (message.startswith("✅") or message.startswith("🧪✅") or message.startswith("🎉") or message.startswith("🌅🎉")):
            # Final success messages
            if "all channels" in message.lower() or "bulk" in message.lower():
                formatted_msg = f"[{timestamp}] {message}\n{'═' * 80}\n\n"
            else:
                formatted_msg = f"[{timestamp}] {message}\n{'━' * 60}\n\n"
        elif message.startswith("❌") or message.startswith("🧪❌"):
            # Error messages
            if "bulk" in message.lower() or "all channels" in message.lower():
                formatted_msg = f"[{timestamp}] {message}\n{'═' * 80}\n\n"
            else:
                formatted_msg = f"[{timestamp}] {message}\n{'━' * 60}\n\n"
        elif message.startswith("  └─"):
            # Sub-items (indented) - no separator, just clean formatting
            formatted_msg = f"[{timestamp}]   {message.replace('└─ ', '└─ ')}\n"
        elif message.startswith("📍") or "Processing channel" in message:
            # Channel processing within bulk operations
            formatted_msg = f"\n[{timestamp}] {message}\n{'─' * 80}\n"
        else:
            # Regular messages (including other progress updates)
            formatted_msg = f"[{timestamp}] {message}\n"
        
        # Only insert to log_text if it exists (logs tab has been created)
        if hasattr(self, 'log_text'):
            self.log_text.insert(tk.END, formatted_msg)
            self.log_text.see(tk.END)
        
        # Also log processing status to main status indicator (if it exists)
        if hasattr(self, 'main_status'):
            if "processing" in message.lower() and ("started" in message.lower() or "starting" in message.lower()):
                self.main_status.config(text="● Processing", foreground='#ff8800')
            elif any(word in message.lower() for word in ["completed", "finished", "success"]):
                # Only set to ready if no critical warnings are shown
                if not (self._warning_shown or self._reddit_warning_shown or self._storage_warning_shown):
                    self.main_status.config(text="● Ready", foreground='#00aa00')
            elif "error" in message.lower() or "failed" in message.lower():
                # Only show error status for critical system errors, not quota/upload errors
                if any(critical_error in message.lower() for critical_error in [
                    "missing", "not found", "config", "credentials", "authentication", 
                    "permission", "access", "storage", "disk", "space"
                ]):
                    self.main_status.config(text="● Error", foreground='#ff0000')
                # Don't change status for quota errors, upload failures, etc.

    def log_section_header(self, title, level="major"):
        """Log a formatted section header with appropriate separators"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if level == "major":
            # For bulk operations or main starts
            separator = "═" * 80
            formatted_msg = f"\n{separator}\n[{timestamp}] {title}\n{separator}\n"
        elif level == "minor":
            # For individual channel processing
            separator = "━" * 60
            formatted_msg = f"\n{separator}\n[{timestamp}] {title}\n{separator}\n"
        elif level == "sub":
            # For sub-sections within a channel
            separator = "─" * 40
            formatted_msg = f"\n[{timestamp}] {title}\n{separator}\n"
        else:
            # Default
            formatted_msg = f"[{timestamp}] {title}\n"
        
        if hasattr(self, 'log_text'):
            self.log_text.insert(tk.END, formatted_msg)
            self.log_text.see(tk.END)
    
    def log_completion(self, message, level="minor"):
        """Log a completion message with appropriate trailing separator"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if level == "major":
            separator = "═" * 80
            formatted_msg = f"[{timestamp}] {message}\n{separator}\n\n"
        elif level == "minor":
            separator = "━" * 60
            formatted_msg = f"[{timestamp}] {message}\n{separator}\n\n"
        else:
            formatted_msg = f"[{timestamp}] {message}\n\n"
        
        if hasattr(self, 'log_text'):
            self.log_text.insert(tk.END, formatted_msg)
            self.log_text.see(tk.END)
    
    def clear_logs(self):
        """Clear the log text"""
        self.log_text.delete(1.0, tk.END)
    
    def save_logs(self):
        """Save logs to file"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            with open(filename, 'w') as f:
                f.write(self.log_text.get(1.0, tk.END))
            self.log_message(f"💾 Logs saved to {filename}")
    
    def open_log_file(self):
        """Open the bot log file"""
        log_file = os.path.join(os.path.dirname(__file__), "bot.log")
        if os.path.exists(log_file):
            os.startfile(log_file)  # Windows
        else:
            messagebox.showinfo("No Log File", "No bot.log file found")
    
    def view_upload_history(self):
        """View upload history for selected channel"""
        selection = self.channels_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a channel")
            return
        
        item = self.channels_tree.item(selection[0])
        channel_label = item['values'][0]
        
        # Open upload history window
        self.show_upload_history(channel_label)
    
    def show_upload_history(self, channel_label):
        """Show upload history window"""
        # Create new window
        history_window = tk.Toplevel(self.root)
        history_window.title(f"Upload History - {channel_label}")
        history_window.geometry("800x600")
        
        # Load upload history
        processed_file = os.path.join(os.path.dirname(__file__), "processed", f"processed_{channel_label}.json")
        uploads = []
        
        if os.path.exists(processed_file):
            try:
                with open(processed_file, 'r') as f:
                    uploads = json.load(f)
            except:
                pass
        
        # Create treeview
        columns = ('Date', 'Title', 'YouTube ID', 'Reddit URL')
        history_tree = ttk.Treeview(history_window, columns=columns, show='headings')
        
        for col in columns:
            history_tree.heading(col, text=col)
            history_tree.column(col, width=150)
        
        # Add scrollbar
        history_scroll = ttk.Scrollbar(history_window, orient=tk.VERTICAL, command=history_tree.yview)
        history_tree.configure(yscrollcommand=history_scroll.set)
        
        # Pack elements
        history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        history_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=10)
        
        # Populate data
        for upload in reversed(uploads):  # Most recent first
            youtube_url = f"https://youtube.com/shorts/{upload.get('youtube_id', '')}"
            history_tree.insert('', tk.END, values=(
                upload.get('date', ''),
                upload.get('title', '')[:50] + '...' if len(upload.get('title', '')) > 50 else upload.get('title', ''),
                upload.get('youtube_id', ''),
                upload.get('url', '')
            ))
        
        # Double-click to open URL
        def on_double_click(event):
            selection = history_tree.selection()
            if selection:
                item = history_tree.item(selection[0])
                youtube_id = item['values'][2]
                if youtube_id:
                    webbrowser.open(f"https://youtube.com/shorts/{youtube_id}")
        
        history_tree.bind('<Double-1>', on_double_click)
    
    def check_startup_profiles(self):
        """Check if any profiles are enabled for startup and run them"""
        startup_profiles = []
        for profile_name, profile in self.profiles.items():
            if profile.get('run_on_startup', False):
                startup_profiles.append(profile_name)
        
        if startup_profiles:
            self.log_message(f"🚀 Found {len(startup_profiles)} profiles enabled for startup")
            response = messagebox.askyesno(
                "Startup Profiles", 
                f"Found {len(startup_profiles)} channel(s) enabled for startup:\n" + 
                "\n".join([f"• {name}" for name in startup_profiles]) + 
                "\n\nRun these channels now?"
            )
            if response:
                self.run_startup_profiles(startup_profiles)
        else:
            self.log_message("ℹ️ No profiles enabled for startup")
    
    def run_startup_profiles(self, profile_names):
        """Run the startup-enabled profiles with daily upload limits"""
        if self.is_processing:
            messagebox.showwarning("Processing", "Already processing. Please wait.")
            return
        
        # Build the processing queue based on daily upload limits
        processing_queue = []
        total_uploads = 0
        
        for profile_name in profile_names:
            profile = self.profiles[profile_name]
            daily_limit = profile.get('daily_upload_limit', 1)
            total_uploads += daily_limit
            
            # Add each upload to the processing queue
            for upload_num in range(daily_limit):
                processing_queue.append({
                    'profile_name': profile_name,
                    'upload_num': upload_num + 1,
                    'daily_limit': daily_limit
                })
        
        process_name = f"Startup processing for {len(profile_names)} channel(s) ({total_uploads} uploads)"
        self.start_processing_mode(process_name)
        self.status_label.config(text=f"Running startup profiles...")
        
        # Auto-switch to logs tab when processing starts
        self.notebook.select(3)  # Index 3 is the logs tab
        
        def process_thread():
            try:
                # Check for abort before starting
                if self.abort_processing:
                    self.processing_queue.put(("abort", f"🛑 Startup process aborted before starting"))
                    return
                
                self.processing_queue.put(("log", f"🌅 Starting startup processing for {len(profile_names)} channel(s) ({total_uploads} uploads)"))
                self.processing_queue.put(("log", ""))  # Add some spacing
                
                for i, item in enumerate(processing_queue):
                    profile_name = item['profile_name']
                    upload_num = item['upload_num']
                    daily_limit = item['daily_limit']
                    
                    progress = (i / total_uploads) * 100
                    self.processing_queue.put(("progress", progress))
                    self.processing_queue.put(("log", f"🎬 Processing {i+1}/{total_uploads}: {profile_name} (Upload {upload_num}/{daily_limit})"))
                    
                    try:
                        # Check for abort before processing each upload
                        if self.abort_processing:
                            self.processing_queue.put(("abort", f"🛑 Startup process aborted during {profile_name} upload {upload_num}"))
                            return
                        
                        profile = self.profiles[profile_name]
                        
                        # Only show profile details on the first upload
                        if upload_num == 1:
                            self.processing_queue.put(("log", f"  └─ Subreddit: r/{profile.get('subreddit', 'unknown')}"))
                            self.processing_queue.put(("log", f"  └─ Music: {profile.get('music_dir', 'default')}"))
                            self.processing_queue.put(("log", f"  └─ Zoom: {profile.get('horizontal_zoom', 1.6)}x"))
                            self.processing_queue.put(("log", f"  └─ Daily Limit: {daily_limit} upload{'s' if daily_limit != 1 else ''}"))
                        
                        # Create an abort check callback function
                        def abort_check_callback():
                            return self.abort_processing
                        
                        # Add abort callback to the profile
                        profile_copy = profile.copy()
                        profile_copy['_gui_abort_callback'] = abort_check_callback
                        profile_copy['_gui_mode'] = True
                        
                        try:
                            pv = load_process_videos()
                            pv.process_channel_with_utf8_recovery(profile_copy)
                        except (UnicodeDecodeError, UnicodeEncodeError) as ue:
                            raise Exception(f"UTF-8 encoding error in startup profile '{profile_name}': {str(ue)}")
                        self.processing_queue.put(("log", f"  └─ ✅ {profile_name} upload {upload_num}/{daily_limit} completed"))
                    except Exception as e:
                        # Handle user abort
                        if "Process aborted by user" in str(e) or self.abort_processing:
                            self.processing_queue.put(("abort", f"🛑 Startup process aborted during {profile_name} upload {upload_num}"))
                            return
                        
                        self.processing_queue.put(("log", f"  └─ ❌ {profile_name} upload {upload_num}/{daily_limit} failed: {str(e)}"))
                
                self.processing_queue.put(("progress", 100))
                self.processing_queue.put(("success", f"🌅🎉 Startup processing completed!"))
                
            except Exception as e:
                # Handle user abort
                if "Process aborted by user" in str(e) or self.abort_processing:
                    self.processing_queue.put(("abort", f"🛑 Startup process aborted"))
                    return
                
                self.processing_queue.put(("error", f"❌ Startup processing error: {str(e)}"))
            finally:
                self.processing_queue.put(("finished", ""))
        
        thread = threading.Thread(target=process_thread, daemon=True)
        thread.start()
    
    def track_profile_changes(self, *args):
        """Track changes to profile variables and mark as unsaved"""
        # Don't track changes during profile loading
        if getattr(self, 'loading_profile', False):
            return
        
        # Also don't track changes if we don't have a selected profile yet
        if not hasattr(self, 'selected_profile') or not self.selected_profile:
            return
        
        # Don't track changes if we don't have original data to compare against
        if not hasattr(self, 'original_profile_data'):
            return
        
        if hasattr(self, 'selected_profile') and self.selected_profile:
            self.has_unsaved_changes = True
            self.update_save_indicator()
    
    def get_current_profile_data(self):
        """Get current profile data from GUI fields"""
        if not hasattr(self, 'profile_vars'):
            return {}
        
        # Build current data in same structure as save_profile_from_editor
        current_data = {
            'label': self.profile_vars.get('label', tk.StringVar()).get(),
            'subreddit': self.profile_vars.get('subreddit', tk.StringVar()).get(),
            'yt_token': self.profile_vars.get('yt_token', tk.StringVar()).get(),
            'music_dir': self.profile_vars.get('music_dir', tk.StringVar()).get(),
            'horizontal_zoom': self.profile_vars.get('horizontal_zoom', tk.DoubleVar()).get(),
            'run_on_startup': self.profile_vars.get('run_on_startup', tk.BooleanVar()).get(),
            'daily_upload_limit': self.profile_vars.get('daily_upload_limit', tk.IntVar()).get(),
        }
        
        # Get hashtags and titles from listboxes
        if hasattr(self, 'hashtags_listbox'):
            hashtags = []
            for i in range(self.hashtags_listbox.size()):
                hashtags.append(self.hashtags_listbox.get(i))
            current_data['hashtags'] = hashtags
        else:
            current_data['hashtags'] = []
            
        if hasattr(self, 'titles_listbox'):
            titles = []
            for i in range(self.titles_listbox.size()):
                titles.append(self.titles_listbox.get(i))
            current_data['sample_titles'] = titles
        else:
            current_data['sample_titles'] = []
        
        # Build nested dictionaries like in save_profile_from_editor
        current_data['video_selection'] = {
            'sort_method': self.profile_vars.get('video_sort_method', tk.StringVar()).get(),
            'enable_fallback': self.profile_vars.get('enable_fallback', tk.BooleanVar()).get()
        }
        
        current_data['font'] = {
            'path': self.profile_vars.get('font_path', tk.StringVar()).get(),
            'size': self.profile_vars.get('font_size', tk.IntVar()).get(),
            'text_position_y': self.profile_vars.get('text_position_y', tk.IntVar()).get()
        }
        
        # Add music mode and volume
        current_data['music_mode'] = self.profile_vars.get('music_mode', tk.StringVar()).get()
        current_data['music_volume'] = self.profile_vars.get('music_volume', tk.DoubleVar()).get()
        
        return current_data
    
    def check_for_unsaved_changes(self):
        """Check if current profile has unsaved changes"""
        if not self.selected_profile:
            return False
        
        # If we don't have original profile data, check if profile exists on disk
        if not hasattr(self, 'original_profile_data'):
            # Check if this profile exists in the saved profiles.json file
            try:
                profiles_file = os.path.join(os.path.dirname(__file__), "profiles.json")
                with open(profiles_file, 'r', encoding='utf-8') as f:
                    file_profiles = json.load(f)
                # If profile doesn't exist on disk, it's unsaved
                return self.selected_profile not in file_profiles
            except Exception:
                # If we can't read the file, assume changes exist
                return True
        
        current_data = self.get_current_profile_data()
        
        # Compare with original data (more robust comparison)
        has_editor_changes = self.compare_profile_data(current_data, self.original_profile_data)
        
        # Also check if the profile exists in the saved file
        try:
            profiles_file = os.path.join(os.path.dirname(__file__), "profiles.json")
            with open(profiles_file, 'r', encoding='utf-8') as f:
                file_profiles = json.load(f)
            
            # If profile doesn't exist on disk, it's definitely unsaved
            if self.selected_profile not in file_profiles:
                return True
                
            # If profile exists on disk, compare with file version (more robust comparison)
            file_profile = file_profiles.get(self.selected_profile, {})
            memory_profile = self.profiles.get(self.selected_profile, {})
            has_memory_changes = self.compare_profile_data(memory_profile, file_profile)
            
            # Return True if either editor or memory has changes
            return has_editor_changes or has_memory_changes
            
        except Exception:
            # If we can't read the file, fall back to editor comparison only
            return has_editor_changes
    
    def compare_profile_data(self, data1, data2):
        """Compare two profile data dictionaries with better handling of defaults and types"""
        if data1 is None or data2 is None:
            return data1 != data2
        
        # Normalize both data dictionaries
        def normalize_profile(data):
            """Normalize profile data for comparison"""
            normalized = {}
            
            # Standard fields with defaults
            defaults = {
                'label': '',
                'subreddit': '',
                'yt_token': '',
                'music_dir': '',
                'horizontal_zoom': 1.6,
                'run_on_startup': False,
                'daily_upload_limit': 1,
                'hashtags': [],
                'sample_titles': [],
                'video_selection': {
                    'sort_method': 'top_month',
                    'enable_fallback': True
                },
                'font': {
                    'path': 'C:\\Windows\\Fonts\\impact.ttf',
                    'size': 70,
                    'text_position_y': 320
                },
                'music_mode': 'smart',
                'music_volume': 0.3
            }
            
            # Apply defaults and normalize types
            for key, default_value in defaults.items():
                if key in data:
                    if key == 'video_selection':
                        # Normalize video_selection dict
                        vs = data.get(key, {})
                        normalized[key] = {
                            'sort_method': vs.get('sort_method', 'top_month'),
                            'enable_fallback': vs.get('enable_fallback', True)
                        }
                    elif key == 'font':
                        # Normalize font dict
                        font = data.get(key, {})
                        normalized[key] = {
                            'path': font.get('path', 'C:\\Windows\\Fonts\\impact.ttf'),
                            'size': int(font.get('size', 70)),
                            'text_position_y': int(font.get('text_position_y', 320))
                        }
                    elif key in ['hashtags', 'sample_titles']:
                        # Ensure lists
                        normalized[key] = list(data.get(key, []))
                    elif key in ['horizontal_zoom', 'music_volume']:
                        # Ensure float with tolerance for comparison
                        value = data.get(key, default_value)
                        try:
                            normalized[key] = round(float(value), 2)  # Round to 2 decimal places
                        except (ValueError, TypeError):
                            normalized[key] = float(default_value)
                    elif key in ['daily_upload_limit']:
                        # Ensure int  
                        value = data.get(key, default_value)
                        try:
                            normalized[key] = int(value)
                        except (ValueError, TypeError):
                            normalized[key] = int(default_value)
                    elif key in ['run_on_startup']:
                        # Ensure bool
                        value = data.get(key, default_value)
                        normalized[key] = bool(value)
                    else:
                        # String fields - ensure string and strip whitespace
                        value = data.get(key, default_value)
                        normalized[key] = str(value).strip() if value is not None else str(default_value)
                else:
                    normalized[key] = default_value
            
            return normalized
        
        norm1 = normalize_profile(data1)
        norm2 = normalize_profile(data2)
        
        return norm1 != norm2

    def update_save_indicator(self):
        """Update the save indicator in the profile editor"""
        if hasattr(self, 'save_indicator'):
            if self.has_unsaved_changes:
                self.save_indicator.config(text="● Unsaved changes", foreground='#ff6600')
            else:
                self.save_indicator.config(text="", foreground='#00aa00')
    
    def prompt_save_changes(self, action_description="continue"):
        """Prompt user to save, discard, or cancel when there are unsaved changes"""
        if not self.has_unsaved_changes:
            return True  # No changes to save
        
        if not self.selected_profile:
            return True  # No profile selected
        
        result = messagebox.askyesnocancel(
            "Unsaved Changes",
            f"You have unsaved changes to '{self.selected_profile}'.\n\n"
            f"Do you want to save your changes before you {action_description}?\n\n"
            f"• Yes: Save changes and {action_description}\n"
            f"• No: Discard changes and {action_description}\n"
            f"• Cancel: Stay on current profile"
        )
        
        if result is True:  # Yes - Save changes
            try:
                # Save the current profile to memory
                self.save_profile_from_editor()
                
                # Actually write to file to persist changes
                profiles_file = os.path.join(os.path.dirname(__file__), "profiles.json")
                with open(profiles_file, 'w', encoding='utf-8') as f:
                    json.dump(self.profiles, f, indent=2, ensure_ascii=False)
                
                self.has_unsaved_changes = False
                self.update_save_indicator()
                self.log_message(f"💾 Saved changes to '{self.selected_profile}' to file before {action_description}")
                return True
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save changes: {str(e)}")
                return False
        elif result is False:  # No - Discard changes
            # Reload the profile to revert UI to original state
            if self.selected_profile:
                self.load_profile_to_editor(self.selected_profile)
            
            self.has_unsaved_changes = False
            self.update_save_indicator()
            self.log_message(f"🗑️ Discarded unsaved changes to '{self.selected_profile}' - reverted to saved state")
            return True
        else:  # Cancel - Stay on current profile
            return False
    
    def on_tab_change(self, event):
        """Handle tab change events to check for unsaved changes"""
        new_tab_index = self.notebook.index("current")
        
        # Check for unsaved changes when leaving the profile tab (index 0)
        if self.current_tab_index == 0 and new_tab_index != 0:  # Leaving profile tab
            # Update unsaved changes flag based on actual comparison
            if hasattr(self, 'selected_profile') and self.selected_profile:
                self.has_unsaved_changes = self.check_for_unsaved_changes()
                
                if self.has_unsaved_changes:
                    # Log that we detected unsaved changes
                    self.log_message(f"⚠️ Detected unsaved changes in profile '{self.selected_profile}' when switching tabs")
                
                if not self.prompt_save_changes("switch tabs"):
                    # User cancelled, revert to profile tab
                    self.root.after_idle(lambda: self.notebook.select(0))
                    return
        
        # Check for unsaved startup changes when leaving the startup tab (index 2)
        elif self.current_tab_index == 2 and new_tab_index != 2:  # Leaving startup tab
            # Check if there are unsaved startup changes
            self.has_unsaved_startup_changes = self.check_for_startup_changes()
            
            if self.has_unsaved_startup_changes:
                # Log that we detected unsaved startup changes
                self.log_message("⚠️ Detected unsaved startup management changes when switching tabs")
                
                if not self.prompt_save_startup_changes("switch tabs"):
                    # User cancelled, revert to startup tab
                    self.root.after_idle(lambda: self.notebook.select(2))
                    return
        
        # Update current tab index
        self.current_tab_index = self.notebook.index("current")
    
    def on_closing(self):
        """Handle window close event to check for unsaved changes"""
        try:
            # Stop any running animations
            if hasattr(self, 'stop_all_animations'):
                self.stop_all_animations()
            
            # Cancel any pending after() calls
            if hasattr(self, 'animation_timer') and self.animation_timer:
                self.root.after_cancel(self.animation_timer)
                
            # Check for unsaved changes if on profile tab
            if hasattr(self, 'current_tab_index') and self.current_tab_index == 0:
                if hasattr(self, 'selected_profile') and self.selected_profile:
                    self.has_unsaved_changes = self.check_for_unsaved_changes()
                    
                    if not self.prompt_save_changes("exit the program"):
                        return  # User cancelled, don't close
            
            # Check for unsaved startup changes if on startup tab
            elif hasattr(self, 'current_tab_index') and self.current_tab_index == 2:
                self.has_unsaved_startup_changes = self.check_for_startup_changes()
                
                if self.has_unsaved_startup_changes:
                    if not self.prompt_save_startup_changes("exit the program"):
                        return  # User cancelled, don't close
            
            # Force cleanup and close
            self.root.quit()  # Exit the mainloop
            self.root.destroy()  # Destroy the window
            
        except Exception as e:
            # If anything fails, force close anyway
            print(f"Error during closing: {e}")
            try:
                self.root.destroy()
            except:
                pass
    
    def store_original_profile_data(self):
        """Store the original profile data for change tracking"""
        if self.selected_profile and hasattr(self, 'profile_vars'):
            self.original_profile_data = self.get_current_profile_data().copy()
            self.has_unsaved_changes = False
            self.update_save_indicator()
    
    def store_original_startup_states(self):
        """Store the original startup states for change tracking"""
        self.original_startup_states = {}
        for name, profile in self.profiles.items():
            self.original_startup_states[name] = profile.get('run_on_startup', False)
        self.has_unsaved_startup_changes = False
    
    def check_for_startup_changes(self):
        """Check if there are unsaved startup changes"""
        for name, profile in self.profiles.items():
            current_startup = profile.get('run_on_startup', False)
            original_startup = self.original_startup_states.get(name, False)
            if current_startup != original_startup:
                return True
        return False
    
    def prompt_save_startup_changes(self, action):
        """Prompt user to save startup changes before performing an action"""
        result = messagebox.askyesnocancel(
            "Unsaved Startup Changes",
            f"You have unsaved startup management changes.\n\n"
            f"Do you want to save them before you {action}?\n\n"
            f"• Click YES to save and continue\n"
            f"• Click NO to discard changes and continue\n"
            f"• Click CANCEL to stay here"
        )
        
        if result is True:  # Save and continue
            self.save_profiles()
            return True
        elif result is False:  # Don't save, but continue
            # Reload original startup states
            for name, original_startup in self.original_startup_states.items():
                if name in self.profiles:
                    self.profiles[name]['run_on_startup'] = original_startup
            self.has_unsaved_startup_changes = False
            self.refresh_startup_display()
            return True
        else:  # Cancel
            return False
    
    def cleanup_unused_tokens(self):
        """Clean up token files that are no longer referenced by any profile"""
        try:
            tokens_dir = os.path.join(os.path.dirname(__file__), "tokens")
            if not os.path.exists(tokens_dir):
                return []
            
            # Get all token files in the tokens directory
            token_files = [f for f in os.listdir(tokens_dir) if f.endswith('.json') and f.startswith('yt_token_')]
            
            # Get all token files referenced by profiles
            used_tokens = set()
            for profile in self.profiles.values():
                token_file = profile.get('yt_token', '')
                if token_file:
                    used_tokens.add(token_file)
            
            # Find unused tokens
            unused_tokens = []
            for token_file in token_files:
                if token_file not in used_tokens:
                    unused_tokens.append(token_file)
            
            return unused_tokens
            
        except Exception as e:
            self.log_message(f"❌ Error checking for unused tokens: {str(e)}")
            return []

    def show_token_management_dialog(self):
        """Show comprehensive token management dialog"""
        from datetime import datetime
        
        dialog = tk.Toplevel(self.root)
        dialog.title("🔑 Token Management")
        dialog.geometry("800x600")
        dialog.configure(bg='#f8f9fa')
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Main frame
        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Title
        ttk.Label(main_frame, text="🔑 Token Management", 
                 font=('Segoe UI', 16, 'bold')).pack(pady=(0, 20))
        
        # Create notebook for different sections
        token_notebook = ttk.Notebook(main_frame)
        token_notebook.pack(fill=tk.BOTH, expand=True)
        
        # Tab 1: Active Tokens
        active_frame = ttk.Frame(token_notebook)
        token_notebook.add(active_frame, text="✅ Active Tokens")
        
        ttk.Label(active_frame, text="Tokens currently used by profiles:", 
                 font=('Segoe UI', 12, 'bold')).pack(pady=(10, 5))
        
        # Active tokens list
        active_list_frame = ttk.Frame(active_frame)
        active_list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        active_tree = ttk.Treeview(active_list_frame, columns=('Profile', 'Token File', 'Status'), show='headings', height=10)
        active_tree.heading('Profile', text='Channel Profile')
        active_tree.heading('Token File', text='Token File')
        active_tree.heading('Status', text='Status')
        
        active_tree.column('Profile', width=200)
        active_tree.column('Token File', width=250)
        active_tree.column('Status', width=150)
        
        active_scroll = ttk.Scrollbar(active_list_frame, orient=tk.VERTICAL, command=active_tree.yview)
        active_tree.configure(yscrollcommand=active_scroll.set)
        
        active_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        active_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Tab 2: Unused Tokens
        unused_frame = ttk.Frame(token_notebook)
        token_notebook.add(unused_frame, text="🗑️ Unused Tokens")
        
        ttk.Label(unused_frame, text="Token files not referenced by any profile:", 
                 font=('Segoe UI', 12, 'bold')).pack(pady=(10, 5))
        
        # Unused tokens list
        unused_list_frame = ttk.Frame(unused_frame)
        unused_list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        unused_tree = ttk.Treeview(unused_list_frame, columns=('Token File', 'Size', 'Modified'), show='headings', height=10)
        unused_tree.heading('Token File', text='Token File')
        unused_tree.heading('Size', text='File Size')
        unused_tree.heading('Modified', text='Last Modified')
        
        unused_tree.column('Token File', width=300)
        unused_tree.column('Size', width=100)
        unused_tree.column('Modified', width=150)
        
        unused_scroll = ttk.Scrollbar(unused_list_frame, orient=tk.VERTICAL, command=unused_tree.yview)
        unused_tree.configure(yscrollcommand=unused_scroll.set)
        
        unused_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        unused_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Unused tokens buttons
        unused_buttons = ttk.Frame(unused_frame)
        unused_buttons.pack(fill=tk.X, pady=10)
        
        def delete_selected_unused():
            """Delete selected unused token files"""
            selection = unused_tree.selection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select token files to delete")
                return
            
            selected_files = []
            for item in selection:
                token_file = unused_tree.item(item)['values'][0]
                selected_files.append(token_file)
            
            if messagebox.askyesno("Delete Unused Tokens", 
                                  f"Delete {len(selected_files)} unused token file(s)?\n\n" +
                                  "\n".join([f"• {f}" for f in selected_files]) +
                                  "\n\nThis action cannot be undone!"):
                deleted_count = 0
                for token_file in selected_files:
                    try:
                        token_path = os.path.join(os.path.dirname(__file__), "tokens", token_file)
                        os.remove(token_path)
                        deleted_count += 1
                        self.log_message(f"🗑️ Deleted unused token: {token_file}")
                    except Exception as e:
                        self.log_message(f"❌ Failed to delete {token_file}: {str(e)}")
                
                messagebox.showinfo("Cleanup Complete", f"Deleted {deleted_count} unused token file(s)")
                refresh_token_lists()
        
        def delete_all_unused():
            """Delete all unused token files"""
            unused_tokens = self.cleanup_unused_tokens()
            if not unused_tokens:
                messagebox.showinfo("No Unused Tokens", "No unused token files found")
                return
            
            if messagebox.askyesno("Delete All Unused Tokens", 
                                  f"Delete ALL {len(unused_tokens)} unused token files?\n\n" +
                                  "\n".join([f"• {f}" for f in unused_tokens[:10]]) +
                                  (f"\n... and {len(unused_tokens) - 10} more" if len(unused_tokens) > 10 else "") +
                                  "\n\nThis action cannot be undone!"):
                deleted_count = 0
                for token_file in unused_tokens:
                    try:
                        token_path = os.path.join(os.path.dirname(__file__), "tokens", token_file)
                        os.remove(token_path)
                        deleted_count += 1
                        self.log_message(f"🗑️ Deleted unused token: {token_file}")
                    except Exception as e:
                        self.log_message(f"❌ Failed to delete {token_file}: {str(e)}")
                
                messagebox.showinfo("Cleanup Complete", f"Deleted {deleted_count} unused token file(s)")
                refresh_token_lists()
        
        ttk.Button(unused_buttons, text="🗑️ Delete Selected", 
                  command=delete_selected_unused, style="Danger.TButton").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(unused_buttons, text="🗑️ Delete All Unused", 
                  command=delete_all_unused, style="Danger.TButton").pack(side=tk.LEFT)
        
        # Tab 3: Rename Tokens
        rename_frame = ttk.Frame(token_notebook)
        token_notebook.add(rename_frame, text="✏️ Rename Tokens")
        
        ttk.Label(rename_frame, text="Rename token files to match current channel names:", 
                 font=('Segoe UI', 12, 'bold')).pack(pady=(10, 5))
        
        # Rename suggestions list
        rename_list_frame = ttk.Frame(rename_frame)
        rename_list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        rename_tree = ttk.Treeview(rename_list_frame, columns=('Profile', 'Current Token', 'Suggested Name'), show='headings', height=10)
        rename_tree.heading('Profile', text='Channel Profile')
        rename_tree.heading('Current Token', text='Current Token File')
        rename_tree.heading('Suggested Name', text='Suggested New Name')
        
        rename_tree.column('Profile', width=200)
        rename_tree.column('Current Token', width=250)
        rename_tree.column('Suggested Name', width=250)
        
        rename_scroll = ttk.Scrollbar(rename_list_frame, orient=tk.VERTICAL, command=rename_tree.yview)
        rename_tree.configure(yscrollcommand=rename_scroll.set)
        
        rename_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        rename_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Rename buttons
        rename_buttons = ttk.Frame(rename_frame)
        rename_buttons.pack(fill=tk.X, pady=10)
        
        def generate_token_filename(profile_label):
            """Generate a standardized token filename from profile label"""
            safe_name = profile_label.lower().replace(" ", "_").replace("-", "_")
            safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")
            return f"yt_token_{safe_name}.json"
        
        def rename_selected_tokens():
            """Rename selected token files"""
            selection = rename_tree.selection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select tokens to rename")
                return
            
            renamed_count = 0
            for item in selection:
                values = rename_tree.item(item)['values']
                profile_name = values[0]
                current_token = values[1]
                suggested_name = values[2]
                
                try:
                    old_path = os.path.join(os.path.dirname(__file__), "tokens", current_token)
                    new_path = os.path.join(os.path.dirname(__file__), "tokens", suggested_name)
                    
                    # Check if new name already exists
                    if os.path.exists(new_path):
                        result = messagebox.askyesno("File Exists", 
                                                   f"Token file '{suggested_name}' already exists.\n\n"
                                                   f"Overwrite it with '{current_token}'?")
                        if not result:
                            continue
                    
                    # Rename the file
                    os.rename(old_path, new_path)
                    
                    # Update the profile to use the new token filename
                    for prof_key, prof_data in self.profiles.items():
                        if prof_data.get('label') == profile_name and prof_data.get('yt_token') == current_token:
                            prof_data['yt_token'] = suggested_name
                            break
                    
                    renamed_count += 1
                    self.log_message(f"✏️ Renamed token: {current_token} → {suggested_name}")
                    
                except Exception as e:
                    self.log_message(f"❌ Failed to rename {current_token}: {str(e)}")
            
            if renamed_count > 0:
                # Save profiles with updated token filenames
                self.save_profiles()
                messagebox.showinfo("Rename Complete", f"Renamed {renamed_count} token file(s)")
                refresh_token_lists()
        
        def auto_rename_all_tokens():
            """Auto-rename all tokens to match channel names"""
            rename_count = 0
            conflicts = []
            
            for profile_key, profile_data in self.profiles.items():
                current_token = profile_data.get('yt_token', '')
                if not current_token:
                    continue
                
                profile_label = profile_data.get('label', profile_key)
                suggested_name = generate_token_filename(profile_label)
                
                if current_token == suggested_name:
                    continue  # Already has correct name
                
                try:
                    old_path = os.path.join(os.path.dirname(__file__), "tokens", current_token)
                    new_path = os.path.join(os.path.dirname(__file__), "tokens", suggested_name)
                    
                    if not os.path.exists(old_path):
                        continue  # Token file doesn't exist
                    
                    if os.path.exists(new_path):
                        conflicts.append((profile_label, current_token, suggested_name))
                        continue
                    
                    # Rename the file
                    os.rename(old_path, new_path)
                    profile_data['yt_token'] = suggested_name
                    rename_count += 1
                    self.log_message(f"✏️ Auto-renamed token: {current_token} → {suggested_name}")
                    
                except Exception as e:
                    self.log_message(f"❌ Failed to auto-rename {current_token}: {str(e)}")
            
            # Save profiles with updated token filenames
            if rename_count > 0:
                self.save_profiles()
            
            # Show results
            result_msg = f"Auto-renamed {rename_count} token file(s)"
            if conflicts:
                result_msg += f"\n\n{len(conflicts)} file(s) had naming conflicts and were skipped:\n"
                result_msg += "\n".join([f"• {c[0]}: {c[1]} → {c[2]}" for c in conflicts[:5]])
                if len(conflicts) > 5:
                    result_msg += f"\n... and {len(conflicts) - 5} more"
            
            messagebox.showinfo("Auto-Rename Complete", result_msg)
            refresh_token_lists()
        
        ttk.Button(rename_buttons, text="✏️ Rename Selected", 
                  command=rename_selected_tokens, style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(rename_buttons, text="🔧 Auto-Rename All", 
                  command=auto_rename_all_tokens, style="TButton").pack(side=tk.LEFT)
        
        def refresh_token_lists():
            """Refresh all token lists in the dialog"""
            # Clear existing items
            for tree in [active_tree, unused_tree, rename_tree]:
                for item in tree.get_children():
                    tree.delete(item)
            
            tokens_dir = os.path.join(os.path.dirname(__file__), "tokens")
            
            # Populate active tokens
            for profile_key, profile_data in self.profiles.items():
                token_file = profile_data.get('yt_token', '')
                if token_file:
                    profile_label = profile_data.get('label', profile_key)
                    token_path = os.path.join(tokens_dir, token_file)
                    status = "✅ Exists" if os.path.exists(token_path) else "❌ Missing"
                    active_tree.insert('', 'end', values=(profile_label, token_file, status))
            
            # Populate unused tokens
            unused_tokens = self.cleanup_unused_tokens()
            for token_file in unused_tokens:
                try:
                    token_path = os.path.join(tokens_dir, token_file)
                    size = os.path.getsize(token_path)
                    size_str = f"{size:,} bytes"
                    modified = datetime.fromtimestamp(os.path.getmtime(token_path)).strftime("%Y-%m-%d %H:%M")
                    unused_tree.insert('', 'end', values=(token_file, size_str, modified))
                except Exception:
                    unused_tree.insert('', 'end', values=(token_file, "Unknown", "Unknown"))
            
            # Populate rename suggestions
            for profile_key, profile_data in self.profiles.items():
                current_token = profile_data.get('yt_token', '')
                if not current_token:
                    continue
                
                profile_label = profile_data.get('label', profile_key)
                suggested_name = generate_token_filename(profile_label)
                
                if current_token != suggested_name:
                    rename_tree.insert('', 'end', values=(profile_label, current_token, suggested_name))
        
        # Bottom buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(20, 0))
        
        ttk.Button(button_frame, text="🔄 Refresh", 
                  command=refresh_token_lists, style="TButton").pack(side=tk.LEFT)
        ttk.Button(button_frame, text="📁 Open Tokens Folder", 
                  command=lambda: os.startfile(os.path.join(os.path.dirname(__file__), "tokens")), 
                  style="TButton").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(button_frame, text="❌ Close", 
                  command=dialog.destroy, style="TButton").pack(side=tk.RIGHT)
        
        # Initial population
        refresh_token_lists()

    def auto_rename_token_on_profile_change(self, old_label, new_label):
        """Automatically rename token file when profile label changes"""
        if not old_label or not new_label or old_label == new_label:
            self.log_message(f"🔍 Debug: Auto-rename skipped - old_label='{old_label}', new_label='{new_label}'")
            return
        
        try:
            # Find the profile that was changed
            profile = None
            for prof_data in self.profiles.values():
                if prof_data.get('label') == new_label:
                    profile = prof_data
                    break
            
            if not profile:
                self.log_message(f"🔍 Debug: No profile found with label '{new_label}'")
                return
                
            if not profile.get('yt_token'):
                self.log_message(f"🔍 Debug: Profile '{new_label}' has no yt_token field")
                return
            
            current_token = profile['yt_token']
            self.log_message(f"🔍 Debug: Current token: '{current_token}'")
            
            # Generate new token filename
            safe_name = new_label.lower().replace(" ", "_").replace("-", "_")
            safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")
            new_token_name = f"yt_token_{safe_name}.json"
            
            self.log_message(f"🔍 Debug: Suggested new token name: '{new_token_name}'")
            
            if current_token == new_token_name:
                self.log_message(f"🔍 Debug: Token already has correct name")
                return  # Already has correct name
            
            # Check if the current token file exists and if new name is available
            tokens_dir = os.path.join(os.path.dirname(__file__), "tokens")
            old_path = os.path.join(tokens_dir, current_token)
            new_path = os.path.join(tokens_dir, new_token_name)
            
            self.log_message(f"🔍 Debug: Token file paths - old: '{old_path}', new: '{new_path}'")
            
            if not os.path.exists(old_path):
                self.log_message(f"🔍 Debug: Original token file doesn't exist: '{old_path}'")
                # Instead of failing, just update the profile to use the new name without renaming
                profile['yt_token'] = new_token_name
                self.log_message(f"✏️ Updated token filename in profile (file doesn't exist): {current_token} → {new_token_name}")
                
                # Refresh the GUI to show the new token name
                if hasattr(self, 'profile_vars') and 'yt_token' in self.profile_vars:
                    self.profile_vars['yt_token'].set(new_token_name)
                    self.log_message(f"🔍 Debug: Updated GUI field to show new token name")
                    
                    # Force GUI to refresh and update all displays
                    self.root.update_idletasks()
                    
                    # Ensure the GUI field doesn't get reset by making sure profile data is consistent
                    if hasattr(self, 'selected_profile') and self.selected_profile in self.profiles:
                        self.profiles[self.selected_profile]['yt_token'] = new_token_name
                        self.log_message(f"🔍 Debug: Ensured profile data consistency for token")
                return
            
            if os.path.exists(new_path):
                # New name already exists, ask user
                self.log_message(f"🔍 Debug: Target token file already exists, asking user for confirmation")
                result = messagebox.askyesno(
                    "Token Rename Conflict",
                    f"Channel label changed: '{old_label}' → '{new_label}'\n\n"
                    f"Auto-rename token file?\n"
                    f"From: {current_token}\n"
                    f"To: {new_token_name}\n\n"
                    f"Warning: Target file already exists and will be overwritten!"
                )
                if not result:
                    self.log_message(f"🔍 Debug: User declined to overwrite existing token file")
                    return
            
            # Rename the token file
            self.log_message(f"🔍 Debug: Attempting to rename token file...")
            os.rename(old_path, new_path)
            profile['yt_token'] = new_token_name
            
            # Refresh the GUI to show the new token name
            if hasattr(self, 'profile_vars') and 'yt_token' in self.profile_vars:
                self.profile_vars['yt_token'].set(new_token_name)
                self.log_message(f"🔍 Debug: Updated GUI field to show new token name")
                
                # Force GUI to refresh and update all displays
                self.root.update_idletasks()
                
                # Ensure the GUI field doesn't get reset by making sure profile data is consistent
                if hasattr(self, 'selected_profile') and self.selected_profile in self.profiles:
                    self.profiles[self.selected_profile]['yt_token'] = new_token_name
                    self.log_message(f"🔍 Debug: Ensured profile data consistency for token")
            
            self.log_message(f"✏️ Auto-renamed token file: {current_token} → {new_token_name}")
            
        except Exception as e:
            self.log_message(f"❌ Failed to auto-rename token file: {str(e)}")
            import traceback
            self.log_message(f"🔍 Debug traceback: {traceback.format_exc()}")

    def quick_cleanup_tokens(self):
        """Quick cleanup of unused tokens without full dialog"""
        unused_tokens = self.cleanup_unused_tokens()
        
        if not unused_tokens:
            messagebox.showinfo("No Unused Tokens", "All token files are currently in use by profiles.")
            return
        
        if messagebox.askyesno("Cleanup Unused Tokens", 
                              f"Found {len(unused_tokens)} unused token file(s):\n\n" +
                              "\n".join([f"• {f}" for f in unused_tokens[:10]]) +
                              (f"\n... and {len(unused_tokens) - 10} more" if len(unused_tokens) > 10 else "") +
                              "\n\nDelete all unused token files?"):
            deleted_count = 0
            for token_file in unused_tokens:
                try:
                    token_path = os.path.join(os.path.dirname(__file__), "tokens", token_file)
                    os.remove(token_path)
                    deleted_count += 1
                    self.log_message(f"🗑️ Deleted unused token: {token_file}")
                except Exception as e:
                    self.log_message(f"❌ Failed to delete {token_file}: {str(e)}")
            
            messagebox.showinfo("Cleanup Complete", f"Deleted {deleted_count} unused token file(s)")

    def run(self):
        """Start the GUI"""
        self.log_message("🎬 YouTube Shorts Bot Manager started")
        
        # Center the window after all GUI elements are created
        self.center_window()
        
        self.root.mainloop()

if __name__ == "__main__":
    # Import tkinter extensions
    try:
        import tkinter.simpledialog
    except ImportError:
        pass
    
    app = YouTubeBotsGUI()
    app.run()


