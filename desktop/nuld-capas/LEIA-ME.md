# Gerenciador de Capas NULD — Retrogames v1.0

Aplicativo para Windows 10/11 de 64 bits. O executável portátil inclui Python e as
bibliotecas: não precisa instalar Python nem conectar o PS2 à internet.

1. Extraia o ZIP em uma pasta do PC e abra **NULD-Capas.exe**.
2. Selecione a raiz do pendrive, onde estão as pastas DVD, CD e/ou POPS.
3. Clique em **Identificar jogos**. PS2: `.iso` em DVD/CD. PS1: `.vcd` em POPS.
4. Se tiver capas do OPL, escolha também a pasta **ART**. Ela tem prioridade sobre a internet.
5. Clique em **Preparar capas**. Sem selecionar linhas, todos os jogos serão processados.
6. Espere concluir, ejete o pendrive pelo Windows e use normalmente no NULD.

O aplicativo identifica o código dentro de SYSTEM.CNF; também aceita códigos no
nome do arquivo. Para jogos sem identificação, dê duplo clique e informe o código
correto da sua edição/região. Não adivinha o código pelo título.

As capas locais aceitam PNG/JPG/JPEG com nomes como `SLUS_213.76_COV.png`,
`SLUS-21376_COV.png` ou `<nome do jogo>_COV.png`. A biblioteca online é a mesma do
NULD: xlenore/ps2-covers e xlenore/psx-covers. Algumas edições não têm capa disponível.

Cada capa gera `covers/SLUS-21376.c16` (256×368) e `covers/SLUS-21376_s.c16`
(184×264). O cache `_h.c16` desse jogo é removido para que o NULD o recrie.
Capas válidas existentes são mantidas por padrão. A conversão usa o formato RGB555
original do projeto, com arredondamento de cores sem dithering para ser rápida no PC.
Os jogos, saves, configurações e a pasta ART não são modificados.

**Cancelar** interrompe entre operações; uma requisição em andamento pode levar até
20 segundos. Aguarde a janela indicar o fim antes de remover o dispositivo.
**Exportar relatório** salva um CSV com resultados e jogos sem capa.

## Limites desta versão

Não monta partições APA/HD Loader, não lê ul.cfg/jogos divididos nem discos compactados
CHD/ZSO. Não acessa o PS2 remotamente: prepara as capas em uma unidade/pasta disponível
no PC, inclusive uma pasta de rede montada pelo Windows. O arquivo final vai para a
raiz do dispositivo de onde o NULD carrega suas capas.

## Executar a partir do código

Na raiz do repositório, com Python 3.11 ou superior:

```sh
python -m pip install -r desktop/nuld-capas/requirements.txt
python desktop/nuld-capas/app.py
```

O workflow **Gerenciador de Capas Windows** gera e testa o executável. Código sob
GPL-3.0. Conversor original de Daniel NULD; veja LICENSE do repositório. Este aplicativo
não possui vínculo oficial com OPL, Sony ou os mantenedores das bibliotecas de capas.
