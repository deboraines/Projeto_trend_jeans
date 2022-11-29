# Imports
import os
import re
import logging
import sqlite3
import requests
import pandas as pd
import numpy as np

from bs4        import BeautifulSoup
from datetime   import datetime
from sqlalchemy import create_engine


# Data Collection
def data_collection(url, headers):

	# Request to URL
	page = requests.get(url, headers = headers)

	# Beautiful soup object
	soup = BeautifulSoup(page.text, 'html.parser')

	# ================================ Product Data ================================
	products = soup.find ('ul', class_='products-listing small')
	product_list = products.find_all('article', class_='hm-product-item')

	# product id
	product_id = [p.get('data-articlecode') for p in product_list]

	# product category
	product_category = [p.get('data-category') for p in product_list]

	# product_name
	product_list = products.find_all('a', class_='link')
	product_name = [p.get_text() for p in product_list]

	# price
	product_list = products.find_all('span', class_='price regular')
	product_price = [p.get_text() for p in product_list]

	data = pd.DataFrame([product_id, product_category, product_name, product_price]).T
	data.columns = ['product_id','product_category','product_name','product_price'] # renomenando as colunas

	return data


# Data Collection by product
def data_collection_by_product(data, headers):

	# Empty dataframe
	df_compositions = pd.DataFrame()

	# # Unique columns for all products
	aux = []

	df_pattern = pd.DataFrame(columns = ['Art. No.', 'Composition', 'Fit', 'Size'])

	# Collecting products
	for i in range (len(data)):
	    # API Requests
	    url = 'https://www2.hm.com/en_us/productpage.' + data.loc[i, 'product_id'] + '.html'
	    logger.debug('Product: %s', url)
	    
	    page = requests.get(url, headers = headers)
	    
	    # Beautiful Soup object
	    soup = BeautifulSoup(page.text, 'html.parser')
	    
	    # ====================================== Color Name ======================================
	    product_list = soup.find_all('a', class_ = 'filter-option miniature active') + soup.find_all('a', class_ = 'filter-option miniature')
	    color_name = [p.get('data-color') for p in product_list]

	    # product id
	    product_id = [p.get('data-articlecode') for p in product_list]

	    df_color = pd.DataFrame([product_id, color_name]).T
	    df_color.columns = ['product_id', 'color_name']
	    
	    # Collecting product information for each color
	    for j in range (len(df_color)):
	        # API Requests
	        url = 'https://www2.hm.com/en_us/productpage.' + df_color.loc[j, 'product_id'] + '.html'
	        logger.debug('Color: %s', url)

	        page = requests.get(url, headers = headers)
	        
	        # Beautiful Soup object
	        soup = BeautifulSoup(page.text, 'html.parser')
	        
	        # ====================================== Product Name ======================================
	        product_name = soup.find_all( 'section', class_='product-name-price')
	        product_name = product_name[0].get_text()
	        
	        # ====================================== Product Price ======================================
	        product_price = soup.find_all( 'div', class_='primary-row product-item-price')
	        product_price = re.findall(r'\d+\.?\d+', product_price[0].get_text())[0]
	    
	        # ====================================== Composition ======================================
	        product_composition_list = soup.find('div', class_='content pdp-text pdp-content').find_all('div')
	        product_composition = [list(filter(None, p.get_text().split('\n'))) for p in product_composition_list]

	        # Rename dataframe
	        df_composition = pd.DataFrame(product_composition).T
	        df_composition.columns = df_composition.iloc[0]

	        # Delete first row
	        df_composition = df_composition.iloc[1:].fillna(method='ffill')

	        # Remove pocket lining, shell, lining and pocket
	        df_composition['Composition'] = df_composition['Composition'].replace('Pocket lining: ', '', regex=True)
	        df_composition['Composition'] = df_composition['Composition'].replace('Pocket: ', '', regex=True)
	        df_composition['Composition'] = df_composition['Composition'].replace('Shell: ', '', regex=True)
	        df_composition['Composition'] = df_composition['Composition'].replace('Lining: ', '', regex=True)

	        # Garantee the same number of columns
	        df_composition = pd.concat([df_pattern, df_composition], axis = 0)

	        # Rename columns
	        df_composition.columns = ['product_id', 'composition', 'fit', 'size']
	        
	        # New columns product_name and product_price
	        df_composition['product_name'] = product_name
	        df_composition['product_price'] = product_price

	        # Keep new columns if it shows up
	        aux = aux + df_composition.columns.tolist()

	        # Merge data color + composition
	        df_composition = pd.merge(df_composition, df_color, how='left', on = 'product_id')

	        # All products
	        df_compositions = pd.concat([df_compositions, df_composition], axis = 0)

	# Join Showroom data + details
	df_compositions['style_id'] = df_compositions['product_id'].apply(lambda x: x[:-3])
	df_compositions['color_id'] = df_compositions['product_id'].apply(lambda x: x[-3:])

	# scrapy datetime
	df_compositions['scrapy_datetime'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

	return df_compositions


# Data Cleanning
def data_cleaning(data_product):
	# product_id
	df_data = data_product.dropna(subset = ['product_id'])

	# product_name
	df_data['product_name'] = df_data['product_name'].str.replace('\n', '')
	df_data['product_name'] = df_data['product_name'].str.replace('\r', '-')
	df_data['product_name'] = df_data['product_name'].apply(lambda x: re.sub(r'-(.+)','', str(x)))
	df_data['product_name'] = df_data['product_name'].str.replace(' ', '_').str.lower()

	# product_price
	df_data['product_price'] = df_data['product_price'].astype(float)

	# color_name
	df_data['color_name'] = df_data['color_name'].str.replace(' ', '_').str.lower()

	# Fit
	df_data['fit'] = df_data['fit'].apply(lambda x: x.replace(' ', '_').lower() if pd.notnull(x) else (x))

	# size model
	df_data['size_model'] = df_data['size'].apply(lambda x: re.search( '\d{3}cm', x).group(0) if pd.notnull(x) else x)
	df_data['size_model'] = df_data['size_model'].apply(lambda x: re.search( '\d+', x).group(0) if pd.notnull(x) else x)

	# size number
	df_data['size_number'] = df_data['size'].str.extract('(\d+/\\d+)')

	# Break composition by comma
	df1 = df_data['composition'].str.split(',', expand = True).reset_index(drop=True)

	# # ================================= Composition =================================

	# Cotton | Spandex | Polyester
	df_ref = pd.DataFrame(index = np.arange(len(df_data)), columns = ['cotton', 'spandex', 'polyester'])

	# ======================= Search for cotton =======================
	df_cotton_0 = df1.loc[df1[0].str.contains('Cotton', na=True), 0]
	df_cotton_0.name = 'cotton'

	df_cotton_1 = df1.loc[df1[1].str.contains('Cotton', na=True), 1]
	df_cotton_1.name = 'cotton'

	# Combine
	df_cotton = df_cotton_0.combine_first(df_cotton_1)

	df_ref = pd.concat( [df_ref, df_cotton], axis=1 )
	df_ref = df_ref.iloc[:, ~df_ref.columns.duplicated(keep = 'last')]

	# ======================= Search for polyester =======================
	df_polyester_0 = df1.loc[df1[0].str.contains('Polyester', na=True), 0]
	df_polyester_0.name = 'polyester'

	df_polyester_1 = df1.loc[df1[1].str.contains('Polyester', na=True), 1]
	df_polyester_1.name = 'polyester'

	# Combine
	df_polyester = df_polyester_0.combine_first(df_polyester_1)

	df_ref = pd.concat([df_ref, df_polyester], axis=1)
	df_ref = df_ref.iloc[:, ~df_ref.columns.duplicated(keep = 'last')] 

	# ======================= Search for spandex =======================
	df_spandex_1 = df1.loc[df1[1].str.contains('Spandex', na=True), 1]
	df_spandex_1.name = 'spandex'

	df_spandex_2 = df1.loc[df1[2].str.contains('Spandex', na=True), 2]
	df_spandex_2.name = 'spandex'

	# Combine
	df_spandex = df_spandex_1.combine_first(df_spandex_2)

	df_ref = pd.concat([df_ref, df_spandex], axis=1)
	df_ref = df_ref.iloc[:, ~df_ref.columns.duplicated(keep = 'last')]

	# Join of combine with product_id
	df_aux = pd.concat([df_data['product_id'].reset_index(drop=True), df_ref], axis=1)

	# Format composition data
	df_aux['cotton'] = df_aux['cotton'].apply(lambda x: int( re.search( '\d+', x).group(0) ) / 100 if pd.notnull(x) else x)
	df_aux['spandex'] = df_aux['spandex'].apply(lambda x: int( re.search( '\d+', x).group(0) ) / 100 if pd.notnull(x) else x)
	df_aux['polyester'] = df_aux['polyester'].apply(lambda x: int( re.search( '\d+', x).group(0) ) / 100 if pd.notnull(x) else x)

	# Final join
	df_aux = df_aux.groupby('product_id').max().reset_index().fillna(0)
	df_data = pd.merge(df_data, df_aux, on='product_id', how='left')

	# Drop columns: excluindo as colunas Size e Composition
	df_data = df_data.drop(columns = ['size','composition'], axis=1)

	# drop duplicates
	df_data = df_data.drop_duplicates().reset_index(drop=True)

	return df_data


#  Data Insert
def data_insert(df_data):
	data_insert = df_data[[
	    'product_id',
	    'style_id',
	    'color_id',
	    'product_name',
	    'color_name',
	    'fit',
	    'product_price',
	    'size_number',
	    'size_model',
	    'cotton',
	    'polyester',
	    'spandex',
	    'scrapy_datetime'
	]]

	# Create database connection
	conn = create_engine( 'sqlite:///hm_database.sqlite', echo=False )

	# Data insert
	data_insert.to_sql('vitrine', con=conn, if_exists='append', index=False)

	return None


if __name__ == '__main__':
	# Logging
	path = '/Users/deboragoncalves/Documents/repos/projeto_trend_jeans/'

	if not os.path.exists(path + 'Logs'):
		os.makedirs(path + 'Logs')

	logging.basicConfig(
		filename = path + 'Logs/webscraping_hm.log'),
		level = logging.DEBUG,
		format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    	datefmt='%Y-%m-%d %H:%M:%S'

    logger = logging.get.Logger('webscraping_hm')

	# Parameter and constants
	headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36'}

	# URL
	url = 'https://www2.hm.com/en_us/men/products/jeans.html'

	# Data collection
	data = data_collection(url, headers)
	logger.info('Data collect done')

	# Data collection by product
	data_product = data_collection_by_product(data, headers)
	logger.info('Data collection by product done')

	# Data cleaning
	data_product_cleaned = data_cleaning(data_product)
	logger.info('Data cleaning done')

	# Data insertion
	data_insert(data_product_cleaned)
	logger.info('Data insertion done')
