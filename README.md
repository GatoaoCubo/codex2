# Bling Product Tools

Este repositório contém utilidades em Python para consultar produtos do ERP Bling.

## Requisitos
- Python 3.10+
- Dependências: `requests`, `pandas`
- Opcional: `gspread` (para exportar ao Google Sheets) e `openai` (para perguntas em linguagem natural)

## Uso rápido
1. Instale as dependências:
   ```bash
   pip install requests pandas gspread openai
   ```
2. Defina a variável `BLING_API_KEY` com sua chave da API, por exemplo:
   ```bash
   export BLING_API_KEY="sua_chave"
   ```
3. Execute o script:
   ```bash
   python3 scripts/bling_products.py
   ```
   Use `--export` para salvar em CSV ou `--gsheet` para exportar para o Google Sheets.
   Os filtros `--category`, `--min-stock`, `--price-min` e `--price-max` ajudam a refinar os resultados. Utilize `--report` para ver um resumo rápido.
4. Para perguntar em linguagem natural, defina `OPENAI_API_KEY` e utilize:
   ```bash
   python3 scripts/bling_products.py --ask "Quantos produtos temos no Bling?"
   ```
