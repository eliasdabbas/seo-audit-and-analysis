import re

import advertools as adv
import pandas as pd
import pyarrow.parquet as pq


def redirect_summary(crawldf):
    """Create a tidy DataFrame for redirects with the columns:

    url: All the URLs in the redirect chain.
    status: The status code of each URL.
    type: "requested", "inermediate", or "crawled".
    order: 1, 2, 3... up to the number of urls in the redirect chain.
    redirect_times: The number of redirects in the chain (URLs in the chain minus one).

    Parameters:
    -----------
    crawldf : pandas.DataFrame
      A DataFrame of an advertools crawl file
    """
    if 'redirect_urls' not in crawldf.columns:
        return pd.DataFrame()
    redirect_df = (crawldf[['url', 'status', 'redirect_urls', 'redirect_reasons']]
                   .dropna(subset=['redirect_urls', 'redirect_reasons']))
    redirect_df['redirect_urls'] = redirect_df['redirect_urls'].str.split('@@')
    redirect_df['redirect_reasons'] = redirect_df['redirect_reasons'].str.split('@@')
    for url, redirect_urls in redirect_df[['url', 'redirect_urls']].values:
        redirect_urls.append(url)
    for status, redirect_reasons in redirect_df[['status', 'redirect_reasons']].values:
        redirect_reasons.append(status)
    redirect_df['order'] = [list(range(1, len(x)+1)) for x in redirect_df['redirect_reasons']]
    redirect_df['type'] = [
        ['requested' if o == min(order) else 'crawled' if o == max(order) else 'intermediate'
          for o in order]
     for order in redirect_df['order']]
    redirect_df.columns = ['NA1', 'NA2', 'url', 'status', 'order', 'type']
    exploded = redirect_df[['url', 'status', 'order', 'type']].apply(pd.Series.explode)
    final_df = pd.merge(exploded, crawldf[['download_latency', 'redirect_times']], left_index=True, right_index=True)
    final_df['redirect_times'] = final_df['redirect_times'].astype(int)
    return final_df


def link_summary(crawldf, internal_url_regex=None):
    """Get a DataFrame summary of links from a crawl DataFrame

    Parameters:
    -----------
    crawldf : DataFrame
      A DataFrame of a website crawled with advertools.
    internal_url_regex : str
      A regular expression for identifying if a link is internal or not.
      For example if your website is example.com, this would be "example.com".

    Returns:
    --------
    link_df : pandas.DataFrame
    """
    link_df = pd.merge(
        crawldf[['url']],
        crawldf.filter(regex='^links_').apply(lambda s: s.str.split('@@').explode()),
        left_index=True, right_index=True)
    link_df['links_nofollow'] = link_df['links_nofollow'].replace({
        'True': True, 'False': False, pd.NA: False})
    link_df.columns = ['url', 'link', 'text', 'nofollow']
    if internal_url_regex is not None:
        link_df['internal'] = link_df['link'].fillna('').str.contains(internal_url_regex, regex=True)
        # link_df.columns.append('internal')
    return link_df


def jl_to_parquet(jl_filepath, parquet_filepath):
    """Convert a jsonlines crawl file to the parquet format.

    Parameters
    ----------
    jl_filepath : str
      The path of an existing .jl file.
    parquet_fileapth : str
      The pather where you want the new file to be saved.    
    """
    status = 'not done'
    crawldf = pd.read_json(jl_filepath, lines=True)
    while status == 'not done':
        try:
            crawldf.to_parquet(parquet_filepath, index=False, version='2.6')
            status = 'done'
        except Exception as e:
            error = e.args[-1]
            column = re.findall('column (\S+)', error)
            print(f'converting to string: {column[0]}')
            crawldf[column[0]] = crawldf[column[0]].astype(str).replace('nan', pd.NA)


def parquet_columns(filepath):
    """Get column names and datatypes of a parquet file.

    Parameters
    ----------
    filepath : str
      The path of the file that you want to get columns names and types.

    Returns
    -------
    columns_types : pandas.DataFrame
      A DataFrame with two columns "column" and "type".
    """
    pqdataset = pq.ParquetDataset(filepath)
    columns_df = pd.DataFrame(
        zip(
            pqdataset.schema.names,
            pqdataset.schema.types),
        columns=['column', 'type'])
    return columns_df


def image_summary(crawldf):
    """Get a DataFrame summary of images in a crawl DataFrame.

    Parameters
    ----------
    crawldf : pandas.DataFrame
      A crawl DataFrame as a result of the advertools.crawl function.

    Returns
    -------
    img_summary : pandas.DataFrame
      A DataFrame containing all available img tags mapped to their respective URLs
      where each image data is represented in a row.
    """
    dfs = []
    img_df = crawldf.filter(regex='^url$|img_')
    for index, row in img_df.iterrows():
        notna = row.dropna().index
        if len(notna) == 1:
            temp = pd.DataFrame({'url': row['url']}, index=[index])
        else:
            temp = row.to_frame().T.set_index('url').apply(lambda s: s.str.split('@@')).explode(notna.tolist()[1:])
            temp = temp.reset_index()
            temp.index = [index for i in range(len(temp))]
        dfs.append(temp)
    final_df = pd.concat(dfs)
    return final_df

def jl_subset(filepath, columns):
    regex = '^' + '$|^'.join(columns) + '$'
    dfs = []
    for chunk in pd.read_json(filepath, lines=True, chunksize=1000):
        chunk_subset = chunk.filter(regex=regex)
        dfs.append(chunk_subset)
    final_df = pd.concat(dfs, ignore_index=True)
    return final_df
