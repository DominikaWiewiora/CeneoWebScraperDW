from app import app
from app import utils
from flask import render_template, request, redirect, url_for, send_file
import requests
import pandas as pd 
import numpy as np
from io import BytesIO
from bs4 import BeautifulSoup
import os
import json
import xlsxwriter
from deep_translator import GoogleTranslator
from matplotlib import pyplot as plt
import matplotlib
matplotlib.use('Agg')

@app.route('/')
@app.route('/index')
def index():
    return render_template("index.html")


@app.route('/extract', methods=['GET', 'POST'])
def extract():
    if request.method == "POST":
        product_id = request.form.get('product_id')
        url = f"https://www.ceneo.pl/{product_id}#tab=reviews"
        response = requests.get(url)
        if response.status_code == requests.codes['ok']:
            page_dom = BeautifulSoup(response.text, "html.parser")
            try:
                opinions_count = page_dom.select_one("a.product-review__link > span").get_text().strip()
            except AttributeError:
                opinions_count = 0
            if opinions_count:
                product_name = page_dom.select_one("h1").get_text().strip()
                all_opinions = []
                while url:
                    print(url)
                    response = requests.get(url)
                    page_dom = BeautifulSoup(response.text, "html.parser")
                    opinions = page_dom.select("div.js_product-review")

                    for opinion in opinions:
                        single_opinion = {
                            key: utils.extract(opinion, *value)
                            for key, value in utils.selectors.items()
                        }
                        for key, transformation in utils.transformations.items():
                            if key in single_opinion and transformation:
                                single_opinion[key] = transformation(single_opinion[key])

                        
                        if 'content_pl' in single_opinion:
                            single_opinion['content_eng'] = utils.translate(single_opinion['content_pl'])
                        
                        
                        if 'pros' in single_opinion:
                            pros_pl = single_opinion['pros']
                            single_opinion['pros'] = {
                                'pl': pros_pl,
                                'eng': utils.translate(pros_pl) if pros_pl else None
                            }
                        if 'cons' in single_opinion:
                            cons_pl = single_opinion['cons']
                            single_opinion['cons'] = {
                                'pl': cons_pl,
                                'eng': utils.translate(cons_pl) if cons_pl else None
                            }

                       
                        ordered_opinion = {
                            'opinion_id': single_opinion.get('opinion_id'),
                            'author': single_opinion.get('author'),
                            'recommendation': single_opinion.get('recommendation'),
                            'score': single_opinion.get('score'),
                            'content_pl': single_opinion.get('content_pl'),
                            'content_eng': single_opinion.get('content_eng'),
                            'pros': single_opinion.get('pros'),
                            'cons': single_opinion.get('cons'),
                            'helpful': single_opinion.get('helpful'),
                            'unhelpful': single_opinion.get('unhelpful'),
                            'publish_date': single_opinion.get('publish_date'),
                            'purchase_date': single_opinion.get('purchase_date')
                        }
                        all_opinions.append(ordered_opinion)

                    try:
                        url = "https://www.ceneo.pl" + utils.extract(page_dom, "a.pagination__next", "href")
                    except TypeError:
                        url = None

                if not os.path.exists("app/opinions"):
                    os.mkdir("app/opinions")
                with open(f"app/opinions/{product_id}.json", "w", encoding="UTF-8") as jf:
                    json.dump(all_opinions, jf, indent=4, ensure_ascii=False)

                
                opinions = pd.DataFrame(all_opinions)

                MAX_SCORE = 5
                opinions.score = opinions.score.apply(lambda s: round(s * MAX_SCORE, 1))
                opinions_count = opinions.index.size
                pros_count = opinions.pros.apply(lambda p: None if not p else p['pl']).count()
                cons_count = opinions.cons.apply(lambda c: None if not c else c['pl']).count()
                average_score = opinions.score.mean()
                score_distribution = opinions.score.value_counts().reindex(np.arange(0, 5.5, 0.5), fill_value=0)
                recommendation_distribution = opinions.recommendation.value_counts(dropna=False).reindex([True, False, np.nan], fill_value=0)

                product = {
                    'product_id': product_id,
                    'product_name': product_name,
                    'opinions_count': int(opinions_count),
                    'pros_count': int(pros_count),
                    'cons_count': int(cons_count),
                    'average_score': average_score,
                    'score_distribution': score_distribution.to_dict(),
                    'recommendation_distribution': recommendation_distribution.to_dict(),
                }

                if not os.path.exists("app/products"):
                    os.mkdir("app/products")
                with open(f"app/products/{product_id}.json", "w", encoding="UTF-8") as jf:
                    json.dump(product, jf, indent=4, ensure_ascii=False)

                if not os.path.exists("app/static"):
                    os.mkdir("app/static")
                if not os.path.exists("app/static/charts"):
                    os.mkdir("app/static/charts")
                fig, ax = plt.subplots()
                score_distribution.plot.bar(color="hotpink")
                plt.xlabel("Number of stars")
                plt.ylabel("Number of opinions")
                plt.title(f"Score histogram for {product_name} product")
                plt.xticks(rotation=0)
                ax.bar_label(ax.containers[0], label_type="edge", fmt=lambda l: int(l) if l else "")
                plt.savefig(f"app/static/charts/{product_id}_score.png")
                recommendation_distribution.plot.pie(
                    labels=["Recommend", "Not recommend", "Indifferent"],
                    label="",
                    colors=["mediumturquoise", "maroon", "silver"],
                    autopct=lambda l: "{:1.1f}%".format(l) if l else ""
                )
                plt.title(f"Recommendation shares for {product_name} product")
                plt.savefig(f"app/static/charts/{product_id}_recommendation.png")

                return redirect(url_for('product', product_id=product_id))
            return render_template("extract.html", error="Product has no opinions")
        return render_template("extract.html", error="Product does not exist")
    return render_template("extract.html")

@app.route('/products')
def products():
    if os.path.exists("app/opinions"):
        products = [filename.split(".")[0] for filename in os.listdir("app/opinions")]
    else: products = []
    products_list = []
    for product in products:
        jf = open(f"app/products/{product}.json", "r", encoding="UTF-8")
        single_product = json.load(jf)
        products_list.append(single_product)
    return render_template("products.html", products = products_list)

@app.route('/author')
def author():
    return render_template("author.html")


@app.route('/product/<product_id>')
def product(product_id):
    opinions = pd.read_json(f'app/opinions/{product_id}.json')
    return render_template("product.html", product_id=product_id, opinions=opinions.to_dict(orient='records'))


@app.route('/charts/<product_id>')
def charts(product_id):
  
    return render_template("charts.html", product_id=product_id)
    



@app.route('/download/json/<product_id>')
def download_json(product_id):
    return send_file(f"opinions/{product_id}.json", mimetype='text/json', download_name=f'{product_id}.json', as_attachment=True)

@app.route('/download/csv/<product_id>')
def download_csv(product_id):
    opinions = pd.read_json(f'app/opinions/{product_id}.json')


    if 'content_pl' in opinions.columns and 'content_eng' in opinions.columns:
        content_pl = opinions['content_pl']
        content_eng = opinions['content_eng']
    
    
    if 'content' in opinions.columns:
        opinions = opinions.drop(columns=['content'])

    response_stream = BytesIO(opinions.to_csv(index=False).encode())
    return send_file(response_stream, mimetype='text/csv', download_name=f'{product_id}.csv', as_attachment=True)


@app.route('/download/xlsx/<product_id>')
def download_xlsx(product_id):
    opinions = pd.read_json(f'app/opinions/{product_id}.json')

  
    if 'content_pl' in opinions.columns and 'content_eng' in opinions.columns:
        content_pl = opinions['content_pl']
        content_eng = opinions['content_eng']
    
    
    if 'content' in opinions.columns:
        opinions = opinions.drop(columns=['content'])

    response_stream = BytesIO()
    opinions.to_excel(response_stream, index=False, engine='xlsxwriter')
    response_stream.seek(0)
    return send_file(response_stream, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', download_name=f'{product_id}.xlsx', as_attachment=True)






