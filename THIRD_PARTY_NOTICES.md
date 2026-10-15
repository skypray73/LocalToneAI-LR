# Third-party components

The project MIT license applies to the original project code and documentation, not to separately licensed dependencies or model weights.

| Component | Distribution | Upstream / license |
|---|---|---|
| YuNet `face_detection_yunet_2023mar.onnx` | Included in `models/`, approximately 227KB | [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet), MIT; full notice in [`models/YuNet-LICENSE.txt`](models/YuNet-LICENSE.txt) |
| OpenCV Python headless | Installed separately by pip | [OpenCV Python](https://github.com/opencv/opencv-python), see wheel/upstream license notices including bundled dependencies |
| NumPy | Installed separately by pip | [NumPy](https://numpy.org/), BSD-3-Clause and bundled notices |
| Pillow | Installed separately by pip | [Pillow](https://python-pillow.org/), HPND and bundled notices |
| Ollama | Downloaded separately by the user | [Ollama](https://github.com/ollama/ollama), MIT and bundled third-party components |
| Qwen3-VL 8B Instruct | Downloaded separately by Ollama; weights not in this repository | [Qwen model card](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct), Apache-2.0; review upstream terms |
| Lua runtime for tests (`lupa`) and PyYAML | Development dependencies only | [Lupa](https://github.com/scoder/lupa), MIT; [PyYAML](https://pyyaml.org/), MIT |

Adobe Lightroom Classic is proprietary software and is not included. Product names and trademarks belong to their respective owners. This project is not endorsed by Adobe, Ollama, or Qwen.
