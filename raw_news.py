import inspect
import kaggle
kaggle.api.authenticate()
kaggle.api.dataset_download_files('rmisra/news-category-dataset', 
                                  path='D:\\End-to-End_News_Collector-Summarizer\\dataset\\', unzip=True)

import pandas as pd
data = pd.read_json('D:\\End-to-End_News_Collector-Summarizer\\dataset\\News_Category_Dataset_v3.json', lines=True)
print(data.head())
print(data.shape)
print(data.columns)

