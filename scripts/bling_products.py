import os
import argparse
import json
from typing import List, Dict, Optional, Tuple

import requests
import pandas as pd

try:
    import gspread
except ImportError:  # pragma: no cover - gspread optional
    gspread = None

try:
    import openai
except ImportError:  # pragma: no cover - openai optional
    openai = None


BLING_API_URL = "https://bling.com.br/Api/v2/produtos/json/"
DEFAULT_SERVICE_ACCOUNT_FILE = "serviceAccountKey.json"


def fetch_products(api_key: str) -> List[Dict]:
    """Retrieve all products from Bling API handling pagination."""
    products: List[Dict] = []
    page = 1
    while True:
        params = {"apikey": api_key, "pagina": page}
        response = requests.get(BLING_API_URL, params=params, timeout=30)
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text}")
        data = response.json().get("retorno", {})
        if "erros" in data:
            raise RuntimeError(f"API error: {data['erros']}")
        page_items = [p["produto"] for p in data.get("produtos", [])]
        products.extend(page_items)
        if len(page_items) < 100:
            break
        page += 1
    return products


def export_to_csv(products: List[Dict], path: str) -> None:
    """Export product list to CSV file."""
    df = pd.DataFrame(products)
    df.to_csv(path, index=False)


def export_to_gsheet(
    products: List[Dict],
    sheet_id: str,
    *,
    worksheet: str = "Produtos",
    creds_file: str = DEFAULT_SERVICE_ACCOUNT_FILE,
) -> None:
    """Export product list to a Google Sheet."""
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


def filter_products(
    products: List[Dict],
    *,
    category: Optional[str] = None,
    min_stock: Optional[float] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
) -> List[Dict]:
    """Filter products by optional category, stock and price range."""
    result = []
    for prod in products:
        if category and prod.get("categoria") != category:
            continue
        estoque = float(prod.get("estoque", 0))
        preco = float(prod.get("preco", 0))
        if min_stock is not None and estoque < min_stock:
            continue
        if price_min is not None and preco < price_min:
            continue
        if price_max is not None and preco > price_max:
            continue
        result.append(prod)
    return result


def ask_gpt(question: str, products: List[Dict]) -> None:
    """Use OpenAI GPT to answer a question about the product list."""
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
    system_msg = (
        "Você é um assistente que ajuda com dúvidas sobre o estoque. "
        "Responda utilizando apenas as informações fornecidas."
    )
    user_msg = (
        f"Temos {total} produtos cadastrados. Abaixo está uma amostra dos dados\n"
        f"{snippet}\n\nPergunta: {question}"
    )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    resp = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
    print(resp.choices[0].message.content.strip())


def generate_report(products: List[Dict]) -> str:
    """Generate a simple summary report from the product list."""
    if not products:
        return "Nenhum produto encontrado."

    df = pd.DataFrame(products)
    total = len(df)
    media_preco = df["preco"].astype(float).mean()
    total_estoque = df["estoque"].astype(float).sum()

    return (
        f"Total de produtos: {total}\n"
        f"Preço médio: R$ {media_preco:.2f}\n"
        f"Estoque total: {total_estoque}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Consulta produtos do Bling")
    parser.add_argument("--export", help="Caminho do CSV para exportar os dados")
    parser.add_argument("--category", help="Filtrar por categoria")
    parser.add_argument("--min-stock", type=float, help="Estoque mínimo para filtrar")
    parser.add_argument("--price-min", type=float, help="Preço mínimo para filtrar")
    parser.add_argument("--price-max", type=float, help="Preço máximo para filtrar")
    parser.add_argument("--ask", help="Pergunta em linguagem natural para a GPT")
    parser.add_argument("--gsheet", help="ID da planilha do Google Sheets")
    parser.add_argument(
        "--worksheet",
        default="Produtos",
        help="Nome da aba ao exportar para o Google Sheets",
    )
    parser.add_argument(
        "--service-account",
        default=DEFAULT_SERVICE_ACCOUNT_FILE,
        help="Caminho do JSON de credencial do Google",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Exibe resumo do estoque",
    )
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
            export_to_gsheet(
                products,
                args.gsheet,
                worksheet=args.worksheet,
                creds_file=args.service_account,
            )
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
