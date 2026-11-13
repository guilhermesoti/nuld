# NULD em português brasileiro

Fork de [danielnuld/nuld](https://github.com/danielnuld/nuld), mantido em
[guilhermesoti/nuld](https://github.com/guilhermesoti/nuld).

## Idioma

Novas configurações começam em português brasileiro. Quem já usa o NULD pode abrir
START → Idioma → Português (Brasil) → Salvar e reiniciar, ou editar
`mass0:/nuld/config.ini`:

```ini
[ui]
idioma = pt-BR
```

Espanhol (`es`) e inglês (`en`) continuam disponíveis. As seções, chaves e valores
internos do INI permanecem no formato original para compatibilidade. O exemplo
`pt-BR/config.ini` tem comentários em português; use-o apenas em instalação nova
ou depois de copiar suas configurações atuais.

## Escopo

Interface do launcher, assistente, opções por jogo, erros de dispositivos e rede,
capas, conquistas e comentários do arquivo de configuração. Fontes foram regeneradas
com acentos portugueses também nos títulos e textos monoespaçados.

O menu durante o jogo contém Reiniciar, Desligar e Cancelar. Para vê-lo em português,
use também `neutrino.elf` e `modules/ee_core.elf` compilados deste fork. O menu antigo
não conhece `-igrlang=pt-BR`. Aplicativos externos, como Jellyfin e POPStarter, têm
código próprio e não são traduzidos por esta alteração.

O arquivo novo deixa `[actualizaciones] buscar = no`: o atualizador embutido aponta
para a versão oficial e poderia substituir a tradução. Configurações existentes
são preservadas; ajuste essa opção manualmente caso já tenha um arquivo anterior.

## Compilação e validação

Consulte o README original para a instalação do PS2SDK. Com ele instalado:

```sh
./build.sh APP=launcher
tools/build_neutrino.sh
```

O workflow **NULD PT-BR** valida a tradução e compila o launcher e o Neutrino,
produzindo um artefato para download na página da execução. A geração dos fontes
não substitui o teste no console real.

Validações locais: fonte 512×384 dentro do limite original de 12 páginas;
autotestes nativos até icon passaram; o teste cover precisa do cabeçalho libjpeg,
ausente no ambiente local. A compilação PS2 é executada pelo GitHub Actions.

Licenças e autoria originais preservadas: GPL-3.0 para NULD e AFL-3.0 para o fork Neutrino.
