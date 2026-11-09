class Plain:
    def __init__(self, text): self.text = text
class Image:
    def __init__(self, path): self.path = path
    async def convert_to_file_path(self): return self.path
class File:
    def __init__(self, name, file="", url=""): self.name, self.file, self.url = name, file, url
    async def get_file(self): return self.file
