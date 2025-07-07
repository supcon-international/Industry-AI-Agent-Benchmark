class Conveyor:
    """
    Conveyor with limited capacity, simulating a production line conveyor belt.
    """
    def __init__(self, capacity):
        """Initialize conveyor with given capacity."""
        self.capacity = capacity
        self.queue = []

    def push(self, product):
        """Add a product to the conveyor. Return True if successful, False if full."""
        if len(self.queue) < self.capacity:
            self.queue.append(product)
            return True
        return False

    def pop(self):
        """Remove and return the first product from the conveyor. Return None if empty."""
        if self.queue:
            return self.queue.pop(0)
        return None

    def is_full(self):
        """Check if the conveyor is full."""
        return len(self.queue) >= self.capacity

    def is_empty(self):
        """Check if the conveyor is empty."""
        return len(self.queue) == 0

    def peek(self):
        """Return the first product without removing it. Return None if empty."""
        if self.queue:
            return self.queue[0]
        return None

class DualBufferConveyor(Conveyor):
    """
    Conveyor with two independent buffers, allowing parallel AGV operations.
    """
    def __init__(self, capacity1, capacity2):
        # 不使用父类的self.queue，改为两个独立buffer
        self.capacity1 = capacity1
        self.capacity2 = capacity2
        self.buffer1 = []
        self.buffer2 = []

    def push(self, product, buffer_index=1):
        """Push product to specified buffer (1 or 2). Return True if successful, False if full."""
        if buffer_index == 1:
            if len(self.buffer1) < self.capacity1:
                self.buffer1.append(product)
                return True
            return False
        elif buffer_index == 2:
            if len(self.buffer2) < self.capacity2:
                self.buffer2.append(product)
                return True
            return False
        else:
            raise ValueError("buffer_index must be 1 or 2")

    def pop(self, buffer_index=1):
        """Pop product from specified buffer (1 or 2). Return product or None if empty."""
        if buffer_index == 1:
            if self.buffer1:
                return self.buffer1.pop(0)
            return None
        elif buffer_index == 2:
            if self.buffer2:
                return self.buffer2.pop(0)
            return None
        else:
            raise ValueError("buffer_index must be 1 or 2")

    def is_full(self, buffer_index=1):
        """Check if specified buffer is full."""
        if buffer_index == 1:
            return len(self.buffer1) >= self.capacity1
        elif buffer_index == 2:
            return len(self.buffer2) >= self.capacity2
        else:
            raise ValueError("buffer_index must be 1 or 2")

    def is_empty(self, buffer_index=1):
        """Check if specified buffer is empty."""
        if buffer_index == 1:
            return len(self.buffer1) == 0
        elif buffer_index == 2:
            return len(self.buffer2) == 0
        else:
            raise ValueError("buffer_index must be 1 or 2")

    def total_size(self):
        """Return total number of products in both buffers."""
        return len(self.buffer1) + len(self.buffer2)

    def has_space(self):
        """Return True if either buffer has space."""
        return (len(self.buffer1) < self.capacity1) or (len(self.buffer2) < self.capacity2)
