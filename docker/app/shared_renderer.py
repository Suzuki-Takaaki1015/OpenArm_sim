"""One MuJoCo 3.6 rendering context shared by sequential camera streams."""
import mujoco

class SharedRenderer(mujoco.Renderer):
    def resize_viewport(self, width, height):
        # Renderer has no public viewport resize API in the pinned MuJoCo 3.6.
        # Keep one GL context/texture upload; only the output viewport changes.
        if not (0 < width <= self.model.vis.global_.offwidth and
                0 < height <= self.model.vis.global_.offheight):
            raise ValueError('Camera viewport exceeds allocated framebuffer')
        self._width, self._height = int(width), int(height)
        self._rect = mujoco.MjrRect(0, 0, self._width, self._height)
        return self
