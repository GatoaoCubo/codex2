import os
import argparse
import json
from typing import List, Dict, Optional

from dotenv import load_dotenv
import requests
import pandas as pd

try:
    import gspread
except ImportError:
    gspread = None

try:
    import openai
except ImportError:
    openai = None

load_dotenv()

BLING_API_URL = "https://api.bling.com.br/v3/produtos"
DEFAULT_SERVICE_ACCOUNT_FILE = "serviceAccountKey.json"

def fetch_products(api_key: str) -> List[Dict]:
    """Busca produtos via API v3 do Bling, com Bearer Token e paginação."""
    products: List[Dict] = []
    page = 1

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    while True:
        params = {"page": page, "limit": 100}
        resp = requests.get(BLING_API_URL, headers=headers, params=params, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
        data = resp.json().get("data", {})
        items = data.get("items", [])
        if not items:
            break
        products.extend(items)
        total = data.get("total", 0)
        if len(products) >= total:
            break
        page += 1

    return products

def export_to_csv(products: List[Dict], path: str) -> None:
    df = pd.DataFrame(products)
    df.to_csv(path, index=False)

def export_to_gsheet(products: List[Dict], sheet_id: str, worksheet: str = "Produtos", creds_file: str = DEFAULT_SERVICE_ACCOUNT_FILE) -> None:
    if gspread is None:
        raise RuntimeError("gspread package not installed")

    client = gspread.service_account(filename=creds_file)
    sh = client.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(worksheet)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet, rows="100", cols="20")
    df = pd.DataFrame(products)
    ws.update([df.columns.values.tolist()] + df.values.tolist())

def filter_products(products: List[Dict], category: Optional[str] = None, min_stock: Optional[float] = None, price_min: Optional[float] = None, price_max: Optional[float] = None) -> List[Dict]:
    result = []
    for prod in products:
        info = prod.get("produto", {})
        if category and info.get("categoria") != category:
            continue
        estoque = float(info.get("estoqueAtual", 0))
        preco = float(info.get("preco", 0))
        if min_stock is not None and estoque < min_stock:
            continue
        if price_min is not None and preco < price_min:
            continue
        if price_max is not None and preco > price_max:
            continue
        result.append(info)
    return result

def ask_gpt(question: str, products: List[Dict]) -> None:
    if openai is None:
        print("openai package not installed.")
        return

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set.")
        return

    openai.api_key = api_key
    total = len(products)
    snippet = json.dumps(products[:10], ensure_ascii=False, indent=2)
    system_msg = "Você é um assistente que ajuda com dúvidas sobre o estoque. Responda utilizando apenas as informações fornecidas."
    user_msg = f"Temos {total} produtos cadastrados. Abaixo está uma amostra dos dados\n{snippet}\n\nPergunta: {question}"
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]
    resp = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
    print(resp.choices[0].message.content.strip())

def generate_report(products: List[Dict]) -> str:
    if not products:
        return "Nenhum produto encontrado."
    df = pd.DataFrame(products)
    total = len(df)
    media_preco = df["preco"].astype(float).mean()
    total_estoque = df["estoqueAtual"].astype(float).sum()
    return f"Total de produtos: {total}\nPreço médio: R$ {media_preco:.2f}\nEstoque total: {total_estoque}"

def main() -> None:
    parser = argparse.ArgumentParser(description="Consulta produtos do Bling")
    parser.add_argument("--export", help="Caminho do CSV para exportar os dados")
    parser.add_argument("--category", help="Filtrar por categoria")
    parser.add_argument("--min-stock", type=float, help="Estoque mínimo para filtrar")
    parser.add_argument("--price-min", type=float, help="Preço mínimo para filtrar")
    parser.add_argument("--price-max", type=float, help="Preço máximo para filtrar")
    parser.add_argument("--ask", help="Pergunta em linguagem natural para a GPT")
    parser.add_argument("--gsheet", help="ID da planilha do Google Sheets")
    parser.add_argument("--worksheet", default="Produtos", help="Nome da aba no Google Sheets")
    parser.add_argument("--service-account", default=DEFAULT_SERVICE_ACCOUNT_FILE, help="Caminho do JSON de credencial do Google")
    parser.add_argument("--report", action="store_true", help="Exibe resumo do estoque")
    args = parser.parse_args()

    api_key = os.getenv("BLING_API_KEY")
    if not api_key:
        raise SystemExit("Defina a variável de ambiente BLING_API_KEY com sua chave da API.")

    try:
        products = fetch_products(api_key)
    except Exception as exc:
        raise SystemExit(f"Falha ao consultar produtos: {exc}")

    products = filter_products(
        products,
        category=args.category,
        min_stock=args.min_stock,
        price_min=args.price_min,
        price_max=args.price_max,
    )

    if args.export:
        export_to_csv(products, args.export)
        print(f"Produtos exportados para {args.export}")

    if args.gsheet:
        try:
            export_to_gsheet(products, args.gsheet, worksheet=args.worksheet, creds_file=args.service_account)
            print("Planilha do Google atualizada.")
        except Exception as exc:
            print(f"Falha ao exportar para Google Sheets: {exc}")

    if args.ask:
        ask_gpt(args.ask, products)
    else:
        for prod in products:
            print(f"{prod.get('codigo')} | {prod.get('descricao')} | R$ {prod.get('preco')}")

    if args.report:
        print("\nResumo:\n" + generate_report(products))

if __name__ == "__main__":
    main()
