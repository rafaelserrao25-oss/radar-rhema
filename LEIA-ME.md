# Radar Rhema

Site de busca de licitações da Rhema, no estilo do Effecti, com dados do PNCP.

## Como funciona
1. `coletar.py` baixa do PNCP todas as licitações **abertas para proposta** no Brasil (concorrência, pregão, dispensa, pré-qualificação e credenciamento).
2. Aplica o funil do `config.json`:
   - **Obras:** só no RN inteiro, nos 23 municípios do CONVALES e até 150 km de Brasília ou de Brasilândia de Minas.
   - **Limpeza urbana** e **mão de obra terceirizada:** Brasil todo.
   - Corta asfalto, aterro, resíduo hospitalar e compra de material.
3. Grava `docs/dados.json`. O site `docs/index.html` lê esse arquivo.
4. No GitHub, o robô (`.github/workflows/atualizar.yml`) começa às **9h e às 15h** (Brasília). A coleta leva cerca de 45 min, então a lista está pronta **antes das 10h e das 16h**.

## Para mudar o funil
Editar `config.json`:
- `bases` → cidades-base e raio em km
- `ufs_inteiras_para_obras` → estados inteiros para obras (hoje: RN)
- `convales.municipios` → municípios com ata
- `trilhas.*.palavras` → palavras que trazem a licitação
- `exclusoes` → palavras que tiram a licitação
- `alertas` → avisos que aparecem no cartão

Escrever sem acento e em minúsculas. Depois, rodar `python coletar.py` (ou esperar a próxima atualização).

## Limites
- Só aparece o que está no PNCP. Edital publicado apenas na plataforma (ex.: BNC) ou no site da prefeitura não aparece. O Effecti cobre esses casos.
- Distância em linha reta, do centro do município.
- Favoritas e descartadas ficam salvas no navegador de cada pessoa (não são compartilhadas).
