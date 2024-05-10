import pathlib

INSTALLER_DIR = pathlib.Path('/opt/google/cuda-installer/')
try:
    INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
except PermissionError:
    pass


K80_DRIVER_VERSION = "470.239.06"
K80_DEVICE_CODE = "10de:102d"
K80_DRIVER_URL = f"https://us.download.nvidia.com/tesla/{K80_DRIVER_VERSION}/NVIDIA-Linux-x86_64-{K80_DRIVER_VERSION}.run"
K80_DRIVER_SHA256_SUM = "7d74caac140a0432d79ebe8e4330dc796f39ba7dd40b3fcd61df760181bf9ccc"

CUDA_TOOLKIT_URL = "https://developer.download.nvidia.com/compute/cuda/12.4.1/local_installers/cuda_12.4.1_550.54.15_linux.run"
CUDA_TOOLKIT_SHA256_SUM = "367d2299b3a4588ab487a6d27276ca5d9ead6e394904f18bccb9e12433b9c4fb"

CUDA_SAMPLES_TARGZ = "https://github.com/NVIDIA/cuda-samples/archive/refs/tags/v12.4.1.tar.gz"
CUDA_SAMPLES_SHA256_SUM = "01bb311cc8f802a0d243700e4abe6a2d402132c9d97ecf2c64f3fbb1006c304c"

CUDA_PROFILE_FILENAME = pathlib.Path("/etc/profile.d/google_cuda_install.sh")
CUDA_BIN_FOLDER = "/usr/local/cuda-12.4/bin"
CUDA_LIB_FOLDER = "/usr/local/cuda-12.4/lib64"

NVIDIA_PERSISTANCED_INSTALLER = "/usr/share/doc/NVIDIA_GLX-1.0/samples/nvidia-persistenced-init.tar.bz2"
