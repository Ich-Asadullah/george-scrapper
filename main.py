import asyncio
import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import time
import sys

from Modules.Pitzl import main_pitzl
from Modules.Edlerid import main_edelrid


# === GUI Logger ===
# This class redirects stdout (like print statements) to the GUI's text widget.
class GUILogger:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, message):
        """Writes a message to the text widget in a thread-safe way."""
        # Ensure UI updates happen on the main thread
        self.text_widget.after(0, self._write, message)

    def _write(self, message):
        self.text_widget.configure(state='normal')
        self.text_widget.insert(tk.END, message)
        self.text_widget.see(tk.END)  # Auto-scroll to the bottom
        self.text_widget.configure(state='disabled')

    def flush(self):
        """Flush method is required for a stream-like object."""
        pass


# === Main GUI Application ===
class ScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Function Runner GUI")
        self.root.geometry("700x550")
        self.root.minsize(500, 400)
        self.root.configure(bg='#f0f0f0')

        # Configure style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('TButton', font=('Arial', 10))
        self.style.configure('TRadiobutton', font=('Arial', 10))
        self.style.configure('TLabelFrame.Label', font=('Arial', 11, 'bold'))

        self.create_widgets()
        
        # Redirect print statements to the GUI logger
        sys.stdout = GUILogger(self.log_text)
        
        print("🚀 Application Ready. Please select a function and click 'Run'.")

    def create_widgets(self):
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.grid(row=0, column=0, sticky="nsew")

        # Configure root grid to make the main frame expandable
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Configure main_frame grid
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1) # Make log section expand

        # --- Options Section ---
        options_frame = ttk.LabelFrame(main_frame, text="Select a Function", padding="10")
        options_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        options_frame.columnconfigure(0, weight=1)
        options_frame.columnconfigure(1, weight=1)
        
        # Radio button variable
        self.choice_var = tk.IntVar(value=1) # Default selection is function 1

        # Radio buttons
        radio1 = ttk.Radiobutton(options_frame, text="Run Pitzl", variable=self.choice_var, value=1)
        radio1.grid(row=0, column=0, sticky='w', padx=5, pady=5)
        
        radio2 = ttk.Radiobutton(options_frame, text="Run Edlerid", variable=self.choice_var, value=2)
        radio2.grid(row=0, column=1, sticky='w', padx=5, pady=5)
        
        # --- Control Section ---
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=1, column=0, sticky="ew", pady=(0, 15))

        self.run_button = ttk.Button(control_frame, text="🚀 Run Selected Function", command=self.start_selected_function)
        self.run_button.pack(side=tk.LEFT, padx=(0, 10))

        clear_button = ttk.Button(control_frame, text="🗑 Clear Log", command=self.clear_log)
        clear_button.pack(side=tk.LEFT)
        
        self.status_label = ttk.Label(control_frame, text="Status: Ready")
        self.status_label.pack(side=tk.RIGHT, padx=10)

        # --- Log Section ---
        log_frame = ttk.LabelFrame(main_frame, text="Logs", padding="10")
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, state='disabled',
                                                 font=("Consolas", 10), wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky="nsew")

    def clear_log(self):
        """Clears the content of the log text widget."""
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
        print("--- Log cleared ---")

    def start_selected_function(self):
        """Starts the chosen function in a new thread to keep the GUI responsive."""
        self.run_button.config(state='disabled')
        self.status_label.config(text="Status: Running...")
        
        selected_option = self.choice_var.get()
        
        if selected_option == 1:
            target_function = main_pitzl
        elif selected_option == 2:
            target_function = main_edelrid
        else:
            print("Error: No valid function selected.")
            self.processing_complete()
            return
            
        # Run the target function in a separate thread
        processing_thread = threading.Thread(target=self.run_worker, args=(target_function,))
        processing_thread.daemon = True # Allows main app to exit even if thread is running
        processing_thread.start()

    def run_worker(self, target_function):
        """Worker that executes the long task and handles completion."""
        try:
            asyncio.run(target_function())
        except Exception as e:
            print(f"\n❌ An error occurred: {e}\n")
        finally:
            # Schedule the UI update on the main thread
            self.root.after(0, self.processing_complete)
    
    def processing_complete(self):
        """Updates the GUI after the task is finished."""
        self.run_button.config(state='normal')
        self.status_label.config(text="Status: Ready")
        print("--- Task finished. Ready for next operation. ---")


# --- Main Execution ---
if __name__ == "__main__":
    root = tk.Tk()
    app = ScraperApp(root)
    root.mainloop()