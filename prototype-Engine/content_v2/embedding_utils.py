from typing import List

import torch
from transformers import BertModel, BertTokenizer


class BGEEmbedder:
    def __init__(self, model_dir: str):
        self.tokenizer = BertTokenizer.from_pretrained(model_dir)
        self.model = BertModel.from_pretrained(model_dir)
        self.model.eval()

    @torch.no_grad()
    def encode(self, texts: List[str], batch_size: int = 32) -> torch.Tensor:
        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            inputs = self.tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            outputs = self.model(**inputs)
            batch_embeddings = outputs.last_hidden_state[:, 0, :]
            batch_embeddings = torch.nn.functional.normalize(batch_embeddings, p=2, dim=1)
            embeddings.append(batch_embeddings)
        return torch.cat(embeddings, dim=0)
