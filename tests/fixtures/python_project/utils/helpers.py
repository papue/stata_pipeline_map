"""Shared utility functions used across the pipeline."""


def normalize_columns(df):
    df.columns = [c.strip().lower() for c in df.columns]
    return df
