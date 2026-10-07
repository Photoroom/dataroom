// The DINOv2 backbones a classifier can train on, mirroring
// SUPPORTED_EMBEDDING_SPACES in backend/dataroom/models/os_image.py.
export const EMBEDDING_SPACES = [
  { value: "vits14", label: "DINOv2 ViT-S/14" },
  { value: "vitb14", label: "DINOv2 ViT-B/14" },
  { value: "vitl14", label: "DINOv2 ViT-L/14" },
  { value: "vitg14", label: "DINOv2 ViT-g/14" },
  { value: "vits14_reg", label: "DINOv2 ViT-S/14 with registers" },
  { value: "vitb14_reg", label: "DINOv2 ViT-B/14 with registers" },
  { value: "vitl14_reg", label: "DINOv2 ViT-L/14 with registers" },
  { value: "vitg14_reg", label: "DINOv2 ViT-g/14 with registers" },
] as const;
