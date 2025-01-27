import requests
import json
import os
import time
import base64
from io import BytesIO
from PIL import Image
import torch
import numpy as np

class RunwayVideoGenerator:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "first_frame": ("IMAGE",),
                "last_frame": ("IMAGE",),
                "promptText": ("STRING", {"default": "A cinematic scene"}),
                "model": ("STRING", {"default": "gen3a_turbo"}),
                "duration": ("INT", {"default": 5, "min": 5, "max": 10}),
                "ratio": (["1280:768", "768:1280"], {"default": "1280:768"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 4294967295}),
                "watermark": ("BOOLEAN", {"default": False}),
                "api_key": ("STRING", {"default": "YOUR_RUNWAY_API_KEY"}),
                "trigger": ("BOOLEAN", {"default": False}),
                "max_wait": ("INT", {"default": 60, "min": 10, "max": 300})
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "IMAGE")  
    RETURN_NAMES = ("video_url", "generation_id", "preview")
    FUNCTION = "generate_video"
    CATEGORY = "runway"

    def encode_image(self, image):
        if isinstance(image, torch.Tensor):
            image = image.squeeze(0)
            image = (image * 255).byte()
            image = Image.fromarray(image.cpu().numpy())
        
        target_size = (384, 384)
        image = image.resize(target_size, Image.Resampling.LANCZOS)
            
        buffered = BytesIO()
        image.save(buffered, format="JPEG", quality=30)
        return base64.b64encode(buffered.getvalue()).decode()

    def poll_status(self, task_id, api_key, max_wait=60):
        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-Runway-Version": "2024-11-06"
        }
        start_time = time.time()
        end_time = start_time + max_wait
        attempts = 0
        
        while time.time() < end_time:
            attempts += 1
            try:
                print(f"Polling attempt {attempts}, time elapsed: {int(time.time() - start_time)}s")
                response = requests.get(
                    f"https://api.dev.runwayml.com/v1/tasks/{task_id}",
                    headers=headers
                )
                response.raise_for_status()
                result = response.json()
                print(f"Task Status Response: {json.dumps(result, indent=2)}")
                
                status = result.get("status", "UNKNOWN")
                print(f"Current status: {status}")
                
                if status == "SUCCEEDED":
                    if "output" in result and len(result["output"]) > 0:
                        result["video_url"] = result["output"][0]
                        return result
                elif status in ["FAILED", "CANCELED"]:
                    raise RuntimeError(f"Task failed: {json.dumps(result, indent=2)}")
                    
                time.sleep(10)
            except Exception as e:
                print(f"Error polling status (attempt {attempts}): {str(e)}")
                if hasattr(e, 'response'):
                    print(f"Response content: {e.response.text}")
                time.sleep(10)
                
        raise RuntimeError(f"Timeout after {max_wait}s and {attempts} polling attempts")

    def generate_video(self, first_frame, last_frame, promptText, model, duration, ratio, seed, watermark, api_key, trigger=False, max_wait=60):
        if not trigger:
            return ("", "", first_frame)

        prompt_images = [
            {
                "uri": f"data:image/jpeg;base64,{self.encode_image(first_frame)}",
                "position": "first"
            },
            {
                "uri": f"data:image/jpeg;base64,{self.encode_image(last_frame)}",
                "position": "last"
            }
        ]

        payload = {
            "promptImage": prompt_images,
            "promptText": promptText,
            "model": model,
            "duration": duration,
            "ratio": ratio,
            "seed": seed,
            "watermark": watermark
        }

        print(f"DEBUG Payload: {json.dumps({k:str(v) if k == 'promptImage' else v for k,v in payload.items()}, indent=2)}")

        try:
            response = requests.post(
                "https://api.dev.runwayml.com/v1/image_to_video",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "X-Runway-Version": "2024-11-06",
                    "Content-Type": "application/json"
                },
                json=payload
            )
            if not response.ok:
                print(f"Error Response: {response.text}")
            response.raise_for_status()
            initial_result = response.json()
            print(f"Initial Response: {json.dumps(initial_result, indent=2)}")
            
            task_id = initial_result.get("id")
            if not task_id:
                raise RuntimeError("No task ID in response")
                
            final_result = self.poll_status(task_id, api_key, max_wait)
            video_url = final_result.get("video_url", "")
            print(f"Video URL: {video_url}")
            return (video_url, task_id, first_frame)
            
        except requests.exceptions.RequestException as e:
            print(f"Error Response: {e.response.text if hasattr(e, 'response') else str(e)}")
            raise RuntimeError(f"Runway API error: {str(e)}")

class RunwayVideoPreview:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_url": ("STRING", {"default": ""}),
                "download": ("BOOLEAN", {"default": False}),
                "filename": ("STRING", {"default": "runway_video.mp4"})
            }
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("video_path",)
    FUNCTION = "preview_video"
    CATEGORY = "runway"

    def preview_video(self, video_url, download=False, filename="runway_video.mp4"):
        if not video_url:
            return ("")
            
        if download:
            try:
                save_path = os.path.join("output", filename)
                response = requests.get(video_url)
                response.raise_for_status()
                
                with open(save_path, "wb") as f:
                    f.write(response.content)
                print(f"Video downloaded to: {save_path}")
                return (save_path,)
            except Exception as e:
                print(f"Error downloading video: {str(e)}")
                return (video_url,)
        return (video_url,)

NODE_CLASS_MAPPINGS = {
    "RunwayVideoGenerator": RunwayVideoGenerator,
    "RunwayVideoPreview": RunwayVideoPreview
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RunwayVideoGenerator": "Runway Video Gen",
    "RunwayVideoPreview": "Runway Video Preview"
}