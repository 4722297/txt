# -*- coding: utf-8 -*-
import os
import json
from typing import Optional
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class RagRetriever:
    """
    RAG retriever that loads the QGIS tool vector database and performs
    semantic search using TF-IDF embeddings (no heavy ML dependencies).
    """

    def __init__(self, db_path=None):
        """
        Initialize the retriever by loading the vector database and building
        a TF-IDF index from tool names, groups, and descriptions.

        :param db_path: Path to the vector database JSON file.
                        Defaults to qgis_vector_db_local.json in the plugin directory.
        """
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), "qgis_vector_db_local.json")

        # Load the vector database
        with open(db_path, "r", encoding="utf-8") as f:
            self.tools = json.load(f)

        # Build text corpus from tool metadata for TF-IDF indexing
        corpus = []
        for tool in self.tools:
            # Combine name, group, description, and id for richer matching
            text = " ".join([
                tool.get("name", ""),
                tool.get("group", ""),
                tool.get("description", ""),
                tool.get("id", "").replace(":", " ").replace("_", " "),
            ])
            corpus.append(text)

        # Fit TF-IDF vectorizer on the tool corpus
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words=None,   # keep all words for multilingual support
            max_features=10000,
            sublinear_tf=True,
            ngram_range=(1, 2),  # unigrams + bigrams for better matching
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)

    def retrieve(self, query: str, top_k: int = 5) -> list:
        """
        Retrieve the top-K most relevant tools for the given query.

        :param query: The user's natural language query.
        :param top_k: Number of top results to return.
        :return: A list of dicts with keys: id, name, group, description, score.
        """
        # Transform the query using the fitted vectorizer
        query_vec = self.vectorizer.transform([query])

        # Compute cosine similarity between query and all tools
        similarities = cosine_similarity(query_vec, self.tfidf_matrix).flatten()

        # Get top-K indices
        top_indices = np.argsort(similarities)[-top_k:][::-1]

        results = []
        for idx in top_indices:
            tool = self.tools[idx]
            results.append({
                "id": tool["id"],
                "name": tool["name"],
                "group": tool["group"],
                "description": tool["description"],
                "score": float(similarities[idx])
            })

        return results

    def get_tool_by_id(self, tool_id: str) -> Optional[dict]:
        """
        Look up a tool by its ID.

        :param tool_id: The tool ID (e.g., 'native:buffer').
        :return: Tool dict (without embedding) or None if not found.
        """
        for tool in self.tools:
            if tool["id"] == tool_id:
                return {
                    "id": tool["id"],
                    "name": tool["name"],
                    "group": tool["group"],
                    "description": tool["description"]
                }
        return None
