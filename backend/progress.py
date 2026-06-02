import time

class ProgressTracker:
    def __init__(self, total_size):
        self.total_size = total_size
        self.downloaded = 0
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.last_downloaded = 0

    def update(self, downloaded):
        """
        Updates progress and calculates stats.
        Returns a dictionary with progress details.
        """
        self.downloaded = downloaded
        current_time = time.time()
        
        # Calculate percentage
        percentage = (self.downloaded / self.total_size) * 100 if self.total_size > 0 else 0
        
        # Calculate speed (bytes per second) - distinct instantaneous speed vs average
        # Let's do simple average for stability or windowed
        elapsed = current_time - self.start_time
        speed = self.downloaded / elapsed if elapsed > 0 else 0
        
        # Calculate ETA
        remaining_bytes = self.total_size - self.downloaded
        eta = remaining_bytes / speed if speed > 0 else 0
        
        return {
            "downloaded_bytes": self.downloaded,
            "total_bytes": self.total_size,
            "percentage": round(percentage, 2),
            "speed_mb_s": round(speed / (1024 * 1024), 2),
            "eta_seconds": round(eta, 0)
        }
