"""Feature extraction using ResNet18."""

import logging
import warnings
import numpy as np

logger = logging.getLogger(__name__)


class FeatureGenerator:
    """Estrae 512-dim feature vector usando ResNet18."""

    def __init__(self):
        self._resnet_model = None

    def extract(self, bbox_image):
        """Estrae feature vector dal bbox image."""
        try:
            import torch
            import torchvision.models as models
            from torchvision import transforms
            from PIL import Image

            # Silenzia warning di PyTorch
            warnings.filterwarnings("ignore", category=UserWarning, module="torch")

            if self._resnet_model is None:
                logger.info("Initializing ResNet18 model...")
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    self._resnet_model = models.resnet18(pretrained=True)
                self._resnet_model = torch.nn.Sequential(*list(self._resnet_model.children())[:-1])
                self._resnet_model.eval()
                if torch.cuda.is_available():
                    self._resnet_model = self._resnet_model.cuda()
                    logger.info("ResNet18 model loaded on GPU")

            if isinstance(bbox_image, np.ndarray):
                bbox_image = Image.fromarray(bbox_image.astype('uint8'))

            transform = transforms.Compose([
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                   std=[0.229, 0.224, 0.225])
            ])
            img_tensor = transform(bbox_image).unsqueeze(0)

            if torch.cuda.is_available():
                img_tensor = img_tensor.cuda()

            with torch.no_grad():
                features_tensor = self._resnet_model(img_tensor)

            features_np = features_tensor.cpu().numpy().flatten()
            return features_np.tobytes()
        except Exception as e:
            logger.error(f"ResNet error: {e}")
            return None
