# Relatório — SimES: simulador de E/S e de sistema de arquivos

**Integrantes:** Betina Borchardt Kusler, Gabriella Schmidt, Lucas Goettert, Lucas Marchese

**Repositório:** https://github.com/borchardtkusler/SISOP-T2

## 0. Resumo

Grupo de quatro integrantes: núcleo completo (N1 a N4), três módulos (M1 cache de blocos, M2 escalonamento
avançado e M6 alocação em disco) e a integração ponta a ponta (X12). Os 22 testes do núcleo, dos três módulos e
da integração passam. Principais resultados: (1) na carga sequencial, o FCFS satura o disco (resposta média de
10,2 s) e o SSTF a resolve (17,4 ms), por atender blocos consecutivos sem pagar rotação; (2) no dispositivo
rápido, o polling gasta menos CPU que a interrupção (0,53% contra 1,12%); (3) o write-back grava 48% menos
blocos que o write-through, mas perde até 55 blocos numa queda de energia e piora a resposta com as rajadas de
sincronização; (4) o DEADLINE mantém a resposta média do SSTF e reduz a maior espera em 25% na carga mais
pesada; (5) a alocação contígua falhou 113 vezes por fragmentação externa com 10% do disco livre; (6) na
integração, a cache absorve as leituras de índice e anula o custo extra da alocação indexada.

## 1. Escopo realizado

| Parte | Situação | Observação |
|---|---|---|
| N1 · Dispositivo (fornecido) | usado | — |
| N2 · Subsistema de E/S (SSTF, SCAN, polling, interrupção) | completo | testes do livro (fila 98, 183, 37, 122, 14, 124, 65, 67) passando |
| N3 · Sistema de arquivos | completo | todos os testes de custo e de erros passando |
| N4 · Experimentos X1–X5 e relatório | completo | resultados oficiais gerados por `experimentos.py` |
| M1 · Cache de blocos (LRU, FIFO, write-through, write-back) | completo | testes do M1 passando; experimento X6 |
| M2 · Escalonamento avançado (C-SCAN, LOOK, C-LOOK, DEADLINE) | completo | exemplos do livro (382, 299 e 322 cilindros) passando; experimento X7 |
| M6 · Alocação (encadeada, FAT, indexada com 2 níveis) | completo | testes do M6 passando; experimento X11 |
| Integração ponta a ponta | completa | teste da integração passando; experimento X12 (com M1 e M6) |
| M3, M4, M5 e bônus flash | não feitos | fora do escopo escolhido pelo grupo |

Resultado dos testes automáticos (`python3 executar.py testes`): `Ran 26 tests — OK (skipped=4)`.
Os 4 testes pulados são os dos módulos M3, M4 e M5, que não fazem parte do escopo escolhido.

## 2. Implementação

### N2 — Subsistema de E/S

**Onde:** `simes/es/escalonadores.py` (classes `SSTF` e `SCAN` e a função auxiliar `_mais_proxima_a_frente`) e `simes/es/cpu.py` (função `custo_cpu`, modos `polling` e `interrupcao`).

**Decisões:** O SSTF escolhe, entre todas as requisições da fila, a de menor distância em cilindros até a cabeça. O `min()` do Python devolve o primeiro mínimo encontrado, o que já cumpre a regra de desempate (vence a que chegou antes). A direção devolvida é a do movimento feito, e é mantida quando o alvo está no mesmo cilindro. O SCAN usa a função `_mais_proxima_a_frente`, que filtra as requisições à frente na direção atual (o mesmo cilindro conta como à frente) e pega a mais próxima, com comparação estrita para preservar a ordem de chegada nos empates. Se nada está à frente, o braço vai até a borda (cilindro 0 ou `max_cilindro`), a direção é invertida e a mais próxima na nova direção é escolhida; a borda entra em `passar_por`. Um caso especial: se a cabeça já está exatamente na borda, `passar_por` fica vazio, porque não há movimento a fazer, e chamar `disco.mover` com distância zero zeraria o último bloco transferido e cobraria uma latência rotacional que não existe. O polling devolve a própria duração do atendimento (espera ocupada durante todo ele). A interrupção devolve `n_blocos × (CUSTO_INTERRUPCAO_MS + CUSTO_COPIA_MS_POR_BLOCO)`, uma interrupção e uma cópia por bloco, conforme as fórmulas do arquivo.

**Dificuldades:** Entender que o SCAN do enunciado vai sempre até a borda (é o SCAN do livro, e não o LOOK) e que o deslocamento da ida até a borda precisa ser devolvido em `passar_por` para entrar no custo. Os testes com o exemplo do livro (deslocamento 236 descendo e 331 subindo) confirmaram a interpretação.

### N3 — Sistema de arquivos

**Onde:** `simes/arquivos/sistema.py`: `resolver`, `_pai_e_nome` (auxiliar nova), `mkdir`, `create`, `open`, `read`, `write`, `seek`, `close` e `unlink`.

**Decisões:**

- **Resolução de caminhos:** O `resolver` parte da raiz e, para cada componente, confere que o nó atual é diretório (senão `ENOTDIR`), lê o bloco do diretório (1 leitura) e procura o nome (senão `ENOENT`). Assim, `/a/b/c` lê `/`, `/a` e `/a/b`, e `/` não lê nada.
- **Leitura até o pai:** As operações que mexem em entradas (`mkdir`, `create`, `unlink`) usam `_pai_e_nome`, que chama o próprio `resolver` no caminho do pai e depois lê o pai. A contagem fica, por construção, igual à do `resolver` no caminho completo, como as regras exigem.
- **Tabelas de arquivos abertos:** A tabela global (`tabela_global`) tem uma `EntradaGlobal` por arquivo, com contador de aberturas de todos os processos; ela é criada na primeira abertura e removida quando o contador zera. A tabela de cada processo (`tabelas_processo[p]`) tem uma `EntradaProcesso` por abertura, com posição e modo próprios. É a organização de dois níveis do Silberschatz (seção 11.1.2): o que é do arquivo fica na tabela global, e o que é de cada abertura fica na do processo.
- **Leitura e escrita:** O `read` limita o intervalo ao tamanho do arquivo, lê só os blocos que contêm os bytes pedidos, avança a posição e devolve quantos bytes leu (0 no fim do arquivo). O `write` estende o arquivo pelo alocador quando a escrita passa do último bloco (e aplica os acessos extras, como as cópias de uma realocação contígua), grava os blocos do intervalo, atualiza tamanho e posição e marca o FCB como sujo. No modo `a`, a posição vai para o fim antes de cada escrita.
- **Metadados no close:** O FCB sujo só é gravado no `close` (1 escrita no bloco do diretório pai). Por isso o `close` de um arquivo só lido custa zero acessos.
- **Unlink de arquivo aberto:** O `unlink` remove a entrada do diretório, decrementa `links` e grava o pai. Os blocos só são liberados se não há mais links e o arquivo não está na tabela global. Caso contrário, quem libera é o `close` que zera o contador. Enquanto isso, quem já tinha o arquivo aberto continua lendo, como no UNIX.
- **Erros:** Modo inválido, tamanho negativo, posição negativa e handle repetido no mesmo processo geram `EINVAL`. Ler sem `r` ou escrever sem `w`/`a` gera `EBADF`. `unlink` de diretório gera `EISDIR` (não há `rmdir` no escopo). Se o alocador lança `ENOSPC` no `mkdir` ou no `create`, o FCB recém-criado é removido de `self.fcbs`, para não ficar órfão.
- **Ganchos:** `_verificar_permissao` é chamado no `open`, e `_verificar_trava` no `read` e no `write`, como pede o arquivo (no núcleo eles não fazem nada).

**Dificuldades:** A regra de custo do `unlink` com arquivo aberto (a liberação adiada para o último `close`) e a distinção entre "ler até o pai" e "resolver o caminho", que acabam tendo a mesma contagem. Os testes `test_unlink_com_arquivo_aberto` e `test_custos_de_criacao` guiaram essas duas partes.

### M1 — Cache de blocos

**Onde:** `simes/es/cache.py`: classe base `_CacheOrdenada` e as classes `CacheLRU` e `CacheFIFO`.

**Decisões:** As duas caches usam a mesma estrutura, um `OrderedDict` que guarda, para cada bloco, se ele está sujo; a ordem do dicionário é a ordem de expulsão (o primeiro sai primeiro). A única diferença entre as políticas é um atributo: a LRU move o bloco para o fim do dicionário a cada uso (leitura ou escrita), e a FIFO nunca muda a ordem depois da entrada. Assim, a comparação do X6 mede só a política de substituição, sem diferenças de implementação. Quando a cache está cheia, `_abrir_espaco` expulsa vítimas e devolve as que estavam sujas, para o simulador gravá-las no disco. No write-through, a escrita devolve o próprio bloco (vai ao disco na hora) e o bloco fica limpo na cache; no write-back, o bloco só é marcado como sujo e vai ao disco na expulsão ou na sincronização periódica (`sincronizar`, a cada 5 s).

**Dificuldades:** Decidir o que fazer quando `inserir` recebe um bloco que já está na cache (pode acontecer quando duas requisições pendentes pedem o mesmo bloco). Optamos por tratar como um uso, sem expulsar ninguém.

### M2 — Escalonamento avançado

**Onde:** `simes/es/escalonadores.py`: classes `CSCAN`, `LOOK`, `CLOOK` e `Deadline`, reaproveitando a função `_mais_proxima_a_frente` do núcleo.

**Decisões:** O **C-SCAN** só atende subindo; sem pedidos acima, devolve `passar_por = [max_cilindro, 0]`, de modo que a volta ao cilindro 0 conta como deslocamento, como pede o enunciado. O **LOOK** é o SCAN sem a ida à borda: sem pedidos à frente, inverte a direção ali mesmo. O **C-LOOK** só atende subindo e, sem pedidos acima, salta direto para o pedido de menor cilindro (o salto conta como deslocamento porque o simulador mede a distância até ele). O **DEADLINE** verifica se algum pedido venceu o prazo (`agora >= req.prazo`, com prazos de 200 ms para leitura e 2 s para escrita); se sim, atende o de prazo mais antigo e mantém a direção; se não, delega a escolha a um SSTF interno.

**Dificuldades:** No DEADLINE, perceber que o prazo vencido não garante espera menor que o prazo: o pedido vencido só é escolhido quando o disco termina o atendimento em curso, e vários podem vencer juntos.

### M6 — Alocação em disco

**Onde:** `simes/arquivos/alocacao.py`: classes `AlocadorEncadeado`, `AlocadorFAT` e `AlocadorIndexado`.

**Decisões:** A **encadeada** reserva os primeiros blocos livres do disco (não precisam ser vizinhos). O acesso ao bloco i segue a corrente a partir de um cursor guardado em `fcb.extra['cursor']`: se i está à frente do cursor, lê os blocos intermediários; se ficou para trás, recomeça do início. Estender custa 1 escrita no antigo último bloco, para gravar o ponteiro. A **FAT** herda os mesmos blocos da encadeada, mas os ponteiros ficam numa tabela em memória, então nem o acesso nem a extensão têm custos extras. A **indexada** reserva primeiro os blocos de índice e depois os de dados; até 1.024 blocos usa um índice de 1 nível, e acima disso, 1 bloco de 1º nível mais ⌈n/1024⌉ de 2º nível. Cada acesso custa 1 leitura de índice (ou 2, nos arquivos grandes), e cada extensão regrava todos os índices. Quando o arquivo passa de 1.024 blocos, o índice antigo vira o de 1º nível e só os de 2º nível são acrescentados.

**Dificuldades:** A transição do índice de 1 para 2 níveis numa extensão, que resolvemos calculando quantos blocos de índice faltam para o novo tamanho (`_n_indices`).

### Integração ponta a ponta

**Onde:** `simes/integracao.py`, função `historico_para_requisicoes`.

**Decisões:** Cada item do histórico da camada de blocos vira uma `Requisicao` com o mesmo instante, processo, tipo, bloco e quantidade de blocos. A lista é ordenada por instante com `sorted`, que é estável, de modo que os acessos de uma mesma operação (que têm o mesmo instante) mantêm a ordem em que foram feitos; depois os ids são numerados de 0 em diante. O X12 roda esse histórico com e sem a cache LRU do M1, com FCFS, SSTF e SCAN, para as alocações contígua e indexada (M6).

## 3. Experimentos

### X1 — Escalonadores sob quatro padrões de carga

**Hipótese:** SSTF e SCAN devem reduzir o deslocamento do braço e o tempo de resposta médio em relação ao FCFS nas quatro cargas. O ganho deve ser maior quando a fila é longa (rajadas) e menor quando a fila é curta. O SSTF deve ter a menor resposta média, mas a maior espera máxima, por favorecer pedidos próximos (risco de inanição). O SCAN deve ter resposta um pouco maior que o SSTF e espera máxima menor, por ser mais justo. Na carga sequencial, o FCFS deve sofrer por alternar entre as duas regiões do disco.

**Fundamentação:** Silberschatz, seção 10.4: o FCFS é justo, mas não otimiza o movimento do braço (10.4.1). O SSTF minimiza a busca a cada passo, mas pode causar inanição (10.4.2). O SCAN varre o disco como um elevador e limita a espera, ao custo de idas até a borda (10.4.3). O livro também observa que, com fila curta, qualquer algoritmo se comporta parecido com o FCFS (10.4.6). No modelo (`parametros.py`), cada atendimento custa busca (1 ms + 0,003 ms por cilindro), rotação (4,17 ms, exceto em leitura sequencial) e transferência (0,04 ms por bloco). O escalonador só reduz a busca, e a sequência perfeita elimina também a rotação.

**Configuração:** Escalonadores FCFS, SSTF e SCAN; disco rígido; CPU por interrupção; 2.000 requisições de 8 blocos em cada carga (sequencial: dois processos varrendo regiões distantes; aleatória; concentrada: 80% dos pedidos nos primeiros 20% do disco; rajadas: 50 pedidos simultâneos a cada 600 ms). Indicadores: deslocamento total, resposta média e no percentil 95, maior espera e vazão.

**Resultados:**

| Carga | Escalonador | Deslocamento (cilindros) | Resposta média (ms) | Resposta p95 (ms) | Maior espera (ms) | Vazão (req/s) |
|---|---|---:|---:|---:|---:|---:|
| sequencial | FCFS | 7.184.093 | 10.241,0 | 19.565,4 | 20.598,1 | 61,5 |
| sequencial | SSTF | 2.336.365 | 17,4 | 32,8 | 37,4 | 167,5 |
| sequencial | SCAN | 2.469.069 | 23,2 | 43,6 | 48,6 | 167,4 |
| aleatória | FCFS | 3.316.472 | 50,1 | 145,1 | 193,5 | 82,5 |
| aleatória | SSTF | 2.631.714 | 21,0 | 48,6 | 116,7 | 82,5 |
| aleatória | SCAN | 3.372.680 | 31,5 | 65,1 | 116,7 | 82,4 |
| concentrada | FCFS | 1.864.164 | 19,8 | 48,6 | 96,0 | 83,8 |
| concentrada | SSTF | 1.613.030 | 15,0 | 37,2 | 130,5 | 83,8 |
| concentrada | SCAN | 3.338.708 | 33,2 | 68,3 | 118,8 | 83,7 |
| rajadas | FCFS | 3.341.490 | 267,0 | 505,3 | 597,3 | 83,5 |
| rajadas | SSTF | 209.811 | 147,5 | 277,7 | 297,0 | 84,4 |
| rajadas | SCAN | 199.955 | 148,6 | 278,7 | 285,4 | 84,4 |

Gráficos: `graficos/X1_resposta_media_ms.png`, `graficos/X1_espera_max_ms.png` e `graficos/X1_deslocamento_total.png`.

Medições de apoio (instrumentação feita à parte, sem alterar a configuração oficial): tamanho médio da fila no momento de cada escolha de 4,3 (FCFS, aleatória), 2,0 (FCFS, concentrada) e 25,5 (rajadas, todos); o SCAN foi até a borda 674 vezes na aleatória e 663 vezes na concentrada (uma vez a cada três pedidos), e só 38 vezes nas rajadas.

**Evidências:** `resultados/es.csv` (linhas com experimento = X1); `graficos/X1_resposta_media_ms.png`; `graficos/X1_espera_max_ms.png`; `graficos/X1_deslocamento_total.png`.

**Análise:**

- **Carga sequencial:** É o caso mais extremo. No FCFS, os pedidos dos dois processos se alternam entre o cilindro ~312 (P1) e o ~3.906 (P2), e cada atendimento faz uma busca de ~3.600 cilindros (≈ 11,8 ms) mais a rotação (4,17 ms): ≈ 16,3 ms por pedido. Como os pedidos chegam, em média, a cada 6 ms, a taxa de chegada é maior que a de serviço, o disco fica 100% ocupado e a fila cresce sem parar (629 pedidos em média). Daí a resposta média de 10 s. O SSTF e o SCAN atendem vários pedidos seguidos do mesmo processo; como esses pedidos são blocos consecutivos, o modelo não cobra a rotação, e o serviço médio cai para ≈ 5,7 ms. A vazão quase triplica (61,5 → 167,5 req/s) e a fila fica em 3 a 4 pedidos. O ganho vem tanto da busca menor quanto da latência rotacional evitada, que o livro trata separadamente.
- **Rajadas:** Confirmam a hipótese de que o ganho cresce com a fila. Com 25 pedidos na fila, em média, SSTF e SCAN reduzem o deslocamento em 16 vezes e a resposta média quase pela metade. A resposta não cai mais porque, no modelo, cada pedido não sequencial paga 4,17 ms de rotação, que nenhum escalonador de busca reduz: dos 5,8 ms de serviço médio do SSTF, 72% são rotação. A vazão quase não muda (84 req/s) porque ela é ditada pelo ritmo das rajadas (50 pedidos a cada 600 ms), e não pelo disco.
- **Aleatória e concentrada:** Aqui a hipótese falhou para o SCAN. Com fila curta (2 a 4 pedidos), o SCAN quase nunca encontra pedidos à frente e vai até a borda a cada três pedidos. Na carga concentrada, 80% dos pedidos estão nos primeiros 1.000 cilindros, mas o SCAN vai até o cilindro 4.999 e volta: o deslocamento é o dobro do FCFS (3,34 milhões contra 1,86 milhão) e a resposta média é 68% maior (33,2 contra 19,8 ms). Na aleatória, o SCAN também desloca mais que o FCFS (3,37 contra 3,32 milhões), embora ainda responda mais rápido (31,5 contra 50,1 ms), porque ordenar os poucos pedidos da fila compensa parte das idas à borda. É exatamente o defeito que o LOOK corrige (inverter na última requisição, sem ir à borda), discutido no livro em 10.4.5.
- **Inanição no SSTF:** Na carga concentrada, a maior espera do SSTF (130,5 ms) passa a do FCFS (96,0 ms): pedidos fora da região quente esperam enquanto chegam pedidos próximos da cabeça. É o efeito previsto no livro. Nas outras cargas a espera máxima do SSTF ficou menor que a do FCFS, porque a fila é curta demais para a inanição se acumular por muito tempo.
- **SSTF × SCAN:** O SSTF teve a menor resposta média em todas as cargas, e o SCAN só teve espera máxima menor que o SSTF nas rajadas e na concentrada, e por pouco. Com 2.000 pedidos e filas curtas, a vantagem de justiça do SCAN aparece pouco nestas cargas.

**Veredito:** PARCIALMENTE CONFIRMADA

### X2 — Polling × interrupção conforme o dispositivo

**Hipótese:** No disco rígido, o polling deve consumir uma fração muito alta da CPU (a CPU fica presa enquanto o disco trabalha), e a interrupção uma fração pequena. No dispositivo rápido, a diferença deve diminuir e pode até se inverter: se o dispositivo termina antes de a CPU pagar o custo de tratar a interrupção e copiar os dados, a espera ocupada sai mais barata.

**Fundamentação:** Silberschatz, seções 13.2.1 e 13.2.2: o polling é eficiente quando o dispositivo é rápido e ineficiente quando a espera é longa; a interrupção libera a CPU, mas cada interrupção tem custo fixo (salvar estado, trocar de contexto, tratar). No modelo, o polling custa a duração do atendimento, e a interrupção custa 0,017 ms por bloco (0,015 de interrupção + 0,002 de cópia). Para um pedido de 8 blocos, a interrupção custa 0,136 ms, enquanto o atendimento leva ≈ 10 ms no disco rígido e 0,064 ms no dispositivo rápido.

**Configuração:** FCFS; dispositivos `hdd` e `rapido`; cargas aleatória e sequencial; modos polling e interrupção. Indicador: `cpu_es_pct`, a porcentagem do tempo total da simulação que a CPU gastou com E/S.

**Resultados:**

| Dispositivo | Carga | Polling (% CPU) | Interrupção (% CPU) | Resposta média (ms) |
|---|---|---:|---:|---:|
| hdd | aleatória | 86,28 | 1,12 | 50,1 |
| hdd | sequencial | 99,998 | 0,84 | 10.241,0 |
| rápido | aleatória | 0,53 | 1,12 | 0,1 |
| rápido | sequencial | 1,07 | 2,28 | 0,1 |

Gráfico: `graficos/X2_cpu.png`. O modo de CPU não muda os tempos de resposta, que dependem só do disco e do escalonador.

**Evidências:** `resultados/es.csv` (linhas com experimento = X2); `graficos/X2_cpu.png`.

**Análise:** No disco rígido, o polling consome exatamente a fração de tempo em que o disco está ocupado: 86,3% na carga aleatória (o disco fica ocioso 13,7% do tempo, entre chegadas) e praticamente 100% na sequencial, onde o FCFS satura o disco (ver X1). Com interrupção, a CPU gasta só 0,136 ms por pedido, ≈ 1%, e fica livre para outros processos durante os ≈ 10 ms de cada atendimento. No dispositivo rápido, a relação se inverte: o atendimento (0,064 ms) é mais curto que o custo das 8 interrupções e cópias (0,136 ms), e o polling gasta cerca de metade da CPU da interrupção (0,53% contra 1,12%). O ponto de equilíbrio do modelo está em 0,017 ms de transferência por bloco: abaixo disso, esperar ocupado é mais barato que ser interrompido. Isso confirma o argumento do livro de que a melhor técnica depende da velocidade do dispositivo. Na carga sequencial do dispositivo rápido, as duas porcentagens dobram porque os pedidos chegam com o dobro da frequência (a cada 6 ms), e não porque cada pedido ficou mais caro.

**Veredito:** CONFIRMADA

### X3 — Acesso sequencial × direto

**Hipótese:** Com o mesmo número de acessos por leitura ou escrita (um bloco), o acesso sequencial do compilador deve ser bem mais rápido por operação que o acesso direto do banco de dados, porque blocos consecutivos não pagam busca nem rotação, enquanto saltos aleatórios num arquivo grande pagam rotação e busca a cada acesso. As operações de metadados (`create`, `open`, `unlink`) devem custar mais no compilador, que trabalha com muitos arquivos pequenos em diretórios.

**Fundamentação:** Silberschatz, seção 11.2: o acesso sequencial lê os registros em ordem, e o acesso direto permite ler qualquer bloco em qualquer ordem, com `seek`. Seção 12.4.1: na alocação contígua, os dois são eficientes em número de acessos, porque o endereço do bloco i é calculado diretamente. Seção 10.1.1: o tempo de cada acesso depende da busca e da latência rotacional. No modelo, só o bloco imediatamente seguinte ao último transferido escapa da rotação de 4,17 ms.

**Configuração:** Alocação contígua; carga `compilador` (175 arquivos criados em diretórios, lidos e escritos em sequência, 600 aberturas, 80 remoções) e carga `banco_dados` (uma tabela de 64 MiB com 3.000 `seek` seguidos de leituras ou escritas de 4 KiB em posições aleatórias, e um log escrito em modo acréscimo). Indicadores: acessos e tempo médio por operação.

**Resultados:**

| Carga | Operação | Quantidade | Acessos médios | Tempo médio (ms) |
|---|---|---:|---:|---:|
| compilador | read | 1.719 | 1,0 | 1,48 |
| compilador | write | 726 | 1,0 | 0,91 |
| compilador | open | 600 | 3,0 | 8,21 |
| compilador | create | 175 | 4,0 | 11,95 |
| compilador | unlink | 80 | 4,0 | 13,69 |
| compilador | close | 600 | 0,2 | 1,05 |
| banco_dados | read | 2.405 | 1,0 | 5,49 |
| banco_dados | write | 1.190 | 1,0 | 5,54 |
| banco_dados | seek | 3.000 | 0,0 | 0,00 |
| banco_dados | open | 2 | 2,0 | 4,25 |

No total, o compilador fez 5.400 acessos em 11.987 ms (2,2 ms por acesso) e o banco de dados fez 3.610 acessos em 19.847 ms (5,5 ms por acesso). Gráfico: `graficos/X3_tempo_por_operacao.png`.

**Evidências:** `resultados/arquivos.csv` e `resultados/arquivos_por_operacao.csv` (linhas com experimento = X3); `graficos/X3_tempo_por_operacao.png`.

**Análise:** O número de acessos por `read` e `write` é igual nas duas cargas (1 bloco), como prevê a alocação contígua: localizar o bloco não custa nada a mais. A diferença está toda no tempo. No banco de dados, quase todo acesso é a um bloco não vizinho do anterior, então paga a rotação de 4,17 ms mais uma busca curta (a tabela ocupa só ~256 cilindros): ≈ 5,5 ms. No compilador, a maioria das leituras e escritas continua de onde a anterior parou e custa só a transferência (0,04 ms); a média de 1,48 ms vem das primeiras leituras de cada arquivo, que pagam a rotação depois do `open`. O `seek` custa zero acessos, porque só muda a posição na tabela do processo; o custo do acesso direto aparece na operação seguinte. O banco de dados fez menos acessos que o compilador e levou 66% mais tempo, o que mostra que, num disco rígido, a ordem dos acessos pesa mais que a quantidade. A segunda parte da hipótese também se confirmou: no compilador, `create` e `unlink` custam 4 acessos (3 leituras de diretório e 1 escrita no pai), e o `open` custa 3, por causa da profundidade dos caminhos. O `close` custa 0,2 acesso em média, porque só os arquivos escritos (FCB sujo) gravam o diretório pai.

**Veredito:** CONFIRMADA

### X4 — Custo de resolver caminhos conforme a profundidade

**Hipótese:** Cada nível de diretório acrescenta uma leitura ao `open`, então os acessos devem crescer linearmente com a profundidade d, na forma d + 1 (a raiz mais os d diretórios). O tempo do `open` também deve crescer linearmente, já que cada leitura de diretório é um acesso ao disco.

**Fundamentação:** Silberschatz, seção 11.3: num diretório em árvore, o caminho absoluto é percorrido componente por componente, e cada diretório precisa ser lido para achar o próximo nome. Seção 12.3: um diretório é um arquivo cujo conteúdo são as entradas. Regra de custo do simulador: `resolver("/a/b/c")` lê `/`, `/a` e `/a/b`.

**Configuração:** Para d = 1 a 10, uma cadeia de d diretórios com um arquivo de 4 KiB no fim, aberto, lido e fechado 20 vezes. Indicadores: acessos e tempo médio por `open`.

**Resultados:**

| Profundidade d | Acessos por `open` | Tempo por `open` (ms) |
|---:|---:|---:|
| 1 | 2 | 4,25 |
| 2 | 3 | 4,29 |
| 3 | 4 | 4,33 |
| 4 | 5 | 4,37 |
| 5 | 6 | 4,41 |
| 6 | 7 | 4,45 |
| 7 | 8 | 4,49 |
| 8 | 9 | 4,53 |
| 9 | 10 | 4,57 |
| 10 | 11 | 4,61 |

Gráfico: `graficos/X4_open_por_profundidade.png`.

**Evidências:** `resultados/arquivos_por_operacao.csv` (linhas com experimento = X4 e operação = open); `resultados/arquivos.csv`; `graficos/X4_open_por_profundidade.png`.

**Análise:** Os acessos seguem exatamente d + 1, o que confirma a primeira parte da hipótese e a regra de custo. O tempo, porém, cresceu apenas 0,04 ms por nível (de 4,25 para 4,61 ms, +8,5% enquanto os acessos aumentaram 5,5 vezes). O motivo está no modelo: os diretórios da cadeia foram criados em sequência e o alocador contíguo, por primeiro encaixe, os colocou em blocos vizinhos (raiz no bloco 0, `n1` no 1, `n2` no 2...). Na resolução, o primeiro diretório paga a rotação (4,17 ms) e cada um dos seguintes é o bloco imediatamente após o anterior, que o modelo cobra só como transferência (0,04 ms). Assim, a profundidade aumenta o trabalho (acessos), mas quase não aumenta o tempo. Num sistema de arquivos com uso real, os diretórios ficam espalhados (criados em momentos diferentes, entre outros arquivos), e cada nível pagaria busca e rotação, ≈ 5 ms. É aí que a cache de diretórios faz diferença (seção 4). A hipótese do tempo linear com inclinação de um acesso aleatório por nível não se confirmou nesta configuração.

**Veredito:** PARCIALMENTE CONFIRMADA

### X5 — Tabelas de arquivos abertos com vários processos

**Hipótese:** A tabela global deve ter no máximo uma entrada por arquivo distinto (12 páginas), não importa quantos processos as abram, enquanto a soma das tabelas por processo deve crescer com o número de aberturas simultâneas. O contador de aberturas deve passar de 1 quando vários processos abrem a mesma página ao mesmo tempo. O `close` de arquivos só lidos não deve acessar o disco.

**Fundamentação:** Silberschatz, seção 11.1.2: o sistema mantém uma tabela de arquivos abertos do sistema (com uma cópia do FCB e o contador de aberturas) e uma tabela por processo (com o ponteiro de posição e o modo). A entrada global só é removida quando o contador chega a zero. Seção 12.2: estruturas em memória do sistema de arquivos.

**Configuração:** Carga `servidor_web`: 12 páginas HTML de 8 a 96 KiB em `/www`, e 8 processos trabalhadores (P1 a P8) que, em 40 rodadas, abrem, leem e fecham páginas sorteadas. Indicadores: tamanho máximo da tabela global, maior tabela de um processo, soma máxima das tabelas por processo e maior contador de aberturas.

**Resultados:**

| Indicador | Valor |
|---|---:|
| Maior tabela global (entradas) | 12 |
| Maior tabela de um processo (entradas) | 3 |
| Maior soma das tabelas por processo | 24 |
| Maior contador de aberturas de um arquivo | 6 |
| `open` (960 operações): acessos médios | 2,0 |
| `read` (4.346 operações): acessos médios | 3,65 |
| `close` (960 operações): acessos médios | 0,0 |

Gráfico: `graficos/X5_tabelas.png`.

**Evidências:** `resultados/arquivos.csv` e `resultados/arquivos_por_operacao.csv` (linhas com experimento = X5); `graficos/X5_tabelas.png`.

**Análise:** No pico, havia 24 aberturas simultâneas (soma das tabelas dos processos) para só 12 entradas na tabela global, uma por página: o dobro de aberturas em relação a arquivos. A tabela global não passa de 12 porque é indexada pelo arquivo, e não pela abertura; com mais processos ou mais rodadas ela continuaria limitada pelo número de arquivos distintos, enquanto a soma das tabelas por processo cresceria. O contador chegou a 6: seis processos tinham a mesma página aberta ao mesmo tempo, cada um com sua própria posição na tabela do processo, o que permite leituras independentes do mesmo arquivo. É a razão de o livro separar as duas tabelas: o que é do arquivo (FCB, contador) é guardado uma vez só, e o que é de cada abertura (posição, modo) fica com o processo. O `close` não custou nenhum acesso porque as páginas só foram lidas e o FCB nunca ficou sujo. O `open` custa 2 leituras (`/` e `/www`), e cada `read` lê em média 3,65 blocos.

**Veredito:** CONFIRMADA

### X6 — Cache de blocos: política de substituição, capacidade e política de escrita (M1)

**Hipótese:** A taxa de acertos deve crescer com a capacidade e se estabilizar quando a cache comportar todos os blocos que a carga usa. A LRU deve acertar mais que a FIFO nas capacidades pequenas, porque a carga tem poucos blocos muito usados, que a LRU mantém e a FIFO expulsa por idade; com cache grande, as duas devem empatar. O write-back deve fazer menos escritas físicas e ter resposta média menor que o write-through, já que a escrita termina na cache, mas deve perder blocos numa queda de energia, enquanto o write-through não perde nenhum.

**Fundamentação:** Silberschatz, seção 13.4.3: a cache guarda cópias de dados para acelerar o acesso, e sua eficácia depende da localidade de referência. Seção 12.6.2: a cache de blocos e as políticas de escrita; a escrita síncrona (write-through) é segura e lenta, a assíncrona (write-back) é rápida e pode perder dados numa queda. Seção 9.4 (substituição de páginas): a FIFO não considera o uso, e a LRU aproxima a política ótima explorando a localidade temporal.

**Configuração:** Carga `reuso`: 3.000 requisições de 1 bloco, 65% leituras, com uma distribuição de Zipf sobre 4.000 blocos (poucos blocos muito acessados); FCFS; disco rígido; queda de energia simulada no meio da carga. Caches LRU e FIFO de 64 a 2.048 blocos, cada uma com write-through e write-back, e uma execução sem cache. Indicadores: taxa de acertos, escritas físicas, resposta média e no percentil 95, blocos sujos perdidos na queda.

**Resultados:**

| Cache | Capacidade | Escrita | Acertos (%) | Escritas físicas | Resposta média (ms) | Resposta p95 (ms) | Perdidos na queda |
|---|---:|---|---:|---:|---:|---:|---:|
| nenhuma | — | — | — | 1.045 | 3.499,95 | 6.427,45 | 0 |
| LRU | 64 | write-through | 39,64 | 1.045 | 74,66 | 211,54 | 0 |
| LRU | 64 | write-back | 39,64 | 715 | 23,36 | 110,36 | 28 |
| LRU | 256 | write-through | 57,75 | 1.045 | 22,05 | 75,93 | 0 |
| LRU | 256 | write-back | 57,70 | 543 | 47,63 | 393,39 | 55 |
| LRU | 1.024 | write-through | 67,06 | 1.045 | 16,89 | 62,59 | 0 |
| LRU | 1.024 | write-back | 67,01 | 541 | 38,93 | 117,20 | 55 |
| FIFO | 64 | write-through | 31,30 | 1.045 | 436,11 | 851,18 | 0 |
| FIFO | 64 | write-back | 33,09 | 810 | 46,27 | 223,50 | 22 |
| FIFO | 256 | write-through | 53,20 | 1.045 | 25,86 | 85,65 | 0 |
| FIFO | 256 | write-back | 53,30 | 607 | 46,35 | 354,14 | 50 |
| FIFO | 1.024 | write-through | 67,06 | 1.045 | 16,89 | 62,59 | 0 |
| FIFO | 1.024 | write-back | 67,01 | 541 | 39,73 | 90,31 | 55 |

As capacidades de 128, 512 e 2.048 blocos estão no CSV. A de 2.048 dá os mesmos números que a de 1.024. Gráficos: `graficos/X6_acerto.png` e `graficos/X6_escrita.png`.

**Evidências:** `resultados/es.csv` (linhas com experimento = X6); `graficos/X6_acerto.png`; `graficos/X6_escrita.png`.

**Análise:**

- **Acertos e capacidade:** A taxa de acertos sobe rápido nas capacidades pequenas e para em 67,06% a partir de 1.024 blocos. Esse teto são as faltas compulsórias: a carga toca cerca de mil blocos distintos, e a primeira referência a cada um sempre falta. Com 1.024 blocos, todos cabem, nada é expulso, e a política de substituição deixa de importar; por isso LRU e FIFO dão exatamente o mesmo resultado a partir daí.
- **LRU × FIFO:** Com 64 blocos, a LRU acerta 39,6% e a FIFO 31,3%. A FIFO expulsa o bloco mais antigo mesmo que ele seja um dos mais usados (na distribuição de Zipf, os blocos populares são justamente os que entraram cedo), enquanto a LRU os mantém porque são usados o tempo todo. Com 64 blocos em write-through, a diferença de acertos vira uma diferença enorme de resposta (74,7 contra 436,1 ms): com as faltas da FIFO, o disco fica perto da saturação, e a fila cresce. O ganho da cache não é proporcional aos acertos quando o disco está no limite.
- **Escritas físicas:** O write-through grava todas as 1.045 escritas. O write-back grava 541 com cache grande, 48% menos, porque vários usuários escrevem os mesmos blocos populares, e dentro de cada intervalo de 5 s só a última versão vai ao disco. A carga escreve em 469 blocos distintos; os 541 gravados indicam que poucos blocos foram regravados em mais de uma sincronização.
- **Queda de energia:** O write-through não perde nada. O write-back perde até 55 blocos, todos os que estavam sujos no instante da queda. É o preço do desempenho, e a razão de sistemas reais combinarem write-back com sincronização periódica e journaling.
- **Resposta média (a parte refutada):** A hipótese de que o write-back responde mais rápido só valeu com caches pequenas (64 e 128 blocos). Com 256 blocos ou mais, o write-back ficou mais lento: 47,6 contra 22,1 ms com 256 blocos, e um percentil 95 de 393 ms. O motivo é a sincronização periódica: a cada 5 s, todos os blocos sujos acumulados no período (cerca de 130 por sincronização: 541 escritas em 4 sincronizações) entram na fila de uma vez, e as leituras que faltam na cache esperam atrás dessa rajada de escritas no FCFS. Com cache pequena, os blocos sujos saem aos poucos, nas expulsões, e a rajada é pequena. O write-through espalha as escritas ao longo do tempo. A média do write-back também é favorecida porque cada escrita do usuário termina na hora, e mesmo assim perdeu.

**Veredito:** PARCIALMENTE CONFIRMADA

### X7 — Escalonamento avançado sob carga crescente (M2)

**Hipótese:** Com o aumento da taxa de chegada, o FCFS deve se degradar primeiro. O SSTF deve manter a menor resposta média, mas com a maior espera máxima entre os algoritmos que otimizam a busca (inanição). LOOK e C-LOOK devem superar SCAN e C-SCAN, porque a carga é concentrada e as idas à borda são desperdício. As versões circulares (C-SCAN, C-LOOK) devem ter espera máxima menor e média maior que as não circulares, por serem mais uniformes. O DEADLINE deve se comportar como o SSTF enquanto nenhum prazo vence e reduzir a espera máxima quando a carga ficar pesada.

**Fundamentação:** Silberschatz, seções 10.4.2 a 10.4.6: SSTF e o risco de inanição; SCAN e C-SCAN; LOOK e C-LOOK como as versões práticas, que só vão até o último pedido; o C-SCAN dá um tempo de espera mais uniforme porque trata o disco como uma lista circular. O DEADLINE segue o `mq-deadline` do Linux, que dá um prazo a cada pedido para evitar inanição (documentação do kernel; seção 4).

**Configuração:** Carga concentrada (80% dos pedidos nos primeiros 20% do disco), 2.000 requisições de 8 blocos, semente 7, com intervalo médio entre chegadas de 14, 11, 9 e 8 ms (de 71 a 125 requisições por segundo); disco rígido; interrupção; os sete escalonadores. Indicadores: resposta média e no percentil 95, maior espera, deslocamento.

**Resultados:** carga mais leve (14 ms) e mais pesada (8 ms); a tabela completa está no CSV.

| Escalonador | Resposta média, 14 ms | Maior espera, 14 ms | Resposta média, 8 ms | Resposta p95, 8 ms | Maior espera, 8 ms | Deslocamento, 8 ms |
|---|---:|---:|---:|---:|---:|---:|
| FCFS | 15,8 | 71,3 | 281,6 | 538,0 | 616,2 | 1.811.896 |
| SSTF | 13,4 | 86,6 | 27,8 | 79,6 | 327,1 | 1.150.844 |
| SCAN | 29,5 | 114,4 | 49,0 | 116,6 | 226,7 | 1.529.626 |
| C-SCAN | 40,1 | 116,9 | 65,8 | 142,1 | 223,1 | 1.589.526 |
| LOOK | 13,8 | 72,8 | 31,4 | 87,5 | 170,3 | 1.165.152 |
| C-LOOK | 14,7 | 102,8 | 38,9 | 100,2 | 163,8 | 1.258.318 |
| DEADLINE | 13,4 | 86,6 | 28,4 | 84,8 | 244,8 | 1.148.860 |

Tempos em ms. Gráficos: `graficos/X7_espera_max_ms.png` e `graficos/X7_resposta_p95_ms.png`.

**Evidências:** `resultados/es.csv` (linhas com experimento = X7); `graficos/X7_espera_max_ms.png`; `graficos/X7_resposta_p95_ms.png`.

**Análise:**

- **FCFS:** Com 14 ms entre chegadas, ele até tem a menor espera máxima (71 ms), porque a fila é curta e ser justo custa pouco. Com 8 ms, o disco satura: a resposta média vai a 282 ms, dez vezes a do SSTF.
- **LOOK × SCAN:** Em todas as cargas, LOOK e C-LOOK foram muito melhores que SCAN e C-SCAN. Com 14 ms, o LOOK responde em 13,8 ms e o SCAN em 29,5 ms, e o SCAN desloca 2,3 vezes mais. É o mesmo efeito do X1: com 80% dos pedidos perto do cilindro 0, ir até o cilindro 4.999 é quase sempre inútil. A diferença diminui com a carga (49,0 contra 31,4 ms com 8 ms), porque a fila mais longa faz as varreduras encontrarem mais pedidos.
- **Inanição do SSTF:** O SSTF tem a menor média em todas as cargas, mas a maior espera máxima entre os algoritmos que otimizam a busca na carga pesada (327 ms, contra 164 a 245 ms dos outros). Pedidos fora da região quente esperam enquanto chegam pedidos próximos da cabeça.
- **Circulares:** O C-LOOK teve a menor espera máxima na carga pesada (163,8 ms), com média 24% maior que a do LOOK. É a troca prevista pelo livro: mais uniformidade, menos desempenho médio. O C-SCAN foi o pior dos quatro "elevadores" em média, porque soma a ida à borda e o retorno ao cilindro 0.
- **DEADLINE:** Com 14 e 11 ms, nenhum pedido chega a esperar 200 ms, e o DEADLINE é idêntico ao SSTF (mesmos números). Com 9 ms, reduz a maior espera de 265,5 para 204,2 ms; com 8 ms, de 327,1 para 244,8 ms (−25%), mantendo a média quase igual (28,4 contra 27,8 ms). A espera máxima passou de 200 ms porque o pedido vencido só é atendido quando o disco termina o atendimento em curso, e vários pedidos vencem juntos. O DEADLINE limita a inanição, mas não dá garantia rígida.
- **Parte refutada:** O DEADLINE não teve a menor espera máxima: LOOK e C-LOOK, que não usam prazos, tiveram esperas máximas menores (170 e 164 ms) nesta carga. O prazo de 200 ms é longo em relação à escala dos tempos de serviço (5 a 15 ms), então ele só age nos casos extremos.

**Veredito:** PARCIALMENTE CONFIRMADA

### X11 — Alocação contígua, encadeada, FAT e indexada (M6)

**Hipótese:** A alocação contígua deve ser a mais barata por acesso, mas, numa partição quase cheia e com arquivos criados e removidos, deve sofrer fragmentação externa: falhas ao crescer arquivos e realocações caras. A encadeada não deve ter fragmentação externa, mas o acesso direto deve ser muito caro, porque é preciso seguir a corrente de ponteiros. A FAT deve resolver isso guardando os ponteiros em memória. A indexada deve ter acesso direto com 1 ou 2 leituras extras de índice e nenhuma fragmentação externa, ao custo dos blocos de índice.

**Fundamentação:** Silberschatz, seção 12.4.1: a alocação contígua tem acesso simples, mas sofre fragmentação externa e dificuldade para crescer arquivos. Seção 12.4.2: a encadeada elimina a fragmentação externa, mas só é eficiente no acesso sequencial; a FAT guarda a tabela de ponteiros no início do volume, normalmente em cache. Seção 12.4.3: a indexada permite acesso direto sem fragmentação externa, com o custo do bloco de índice e esquemas de vários níveis para arquivos grandes. Seção 12.5: o mapa de bits do espaço livre.

**Configuração:** Partição de 20.000 blocos; carga `alocacao`: cria arquivos de 1 a 256 blocos até ocupar 70% do disco, remove 40% deles, cria mais até 85%, estende 60 arquivos com escritas em modo acréscimo e faz 100 leituras em posições aleatórias em cada um dos 5 maiores arquivos, seguidas de uma leitura completa. Indicadores: acessos e tempo por operação, falhas de alocação, realocações e trechos livres.

**Resultados:**

| Alocador | Acessos por operação | Tempo médio por operação (ms) | Tempo total (ms) | Falhas (ENOSPC) | Realocações | Trechos livres | Maior trecho livre |
|---|---:|---:|---:|---:|---:|---:|---:|
| contígua | 7,35 | 34,55 | 85.273,7 | 113 | 59 | 50 | 154 |
| encadeada | 77,52 | 12,73 | 31.412,7 | 0 | 0 | 1 | 1.939 |
| FAT | 1,90 | 4,01 | 9.886,2 | 0 | 0 | 1 | 1.939 |
| indexada | 4,29 | 14,32 | 35.345,4 | 0 | 0 | 1 | 1.805 |

| Alocador | `read`: acessos | `read`: ms | `write`: acessos | `write`: ms | `create`: acessos |
|---|---:|---:|---:|---:|---:|
| contígua | 3,04 | 4,41 | 15,10 | 77,98 | 3,0 |
| encadeada | 74,91 | 6,40 | 142,86 | 24,47 | 3,0 |
| FAT | 3,06 | 4,43 | 2,00 | 4,66 | 3,0 |
| indexada | 6,12 | 18,98 | 5,00 | 19,97 | 7,0 |

Gráficos: `graficos/X11_alocacao.png` e `graficos/X11_fragmentacao.png`.

**Evidências:** `resultados/arquivos.csv` e `resultados/arquivos_por_operacao.csv` (linhas com experimento = X11); `graficos/X11_alocacao.png`; `graficos/X11_fragmentacao.png`.

**Análise:**

- **Contígua (fragmentação externa):** No fim da carga havia 2.052 blocos livres (10% do disco), mas espalhados em 50 trechos, o maior com 154 blocos. Por isso, 113 escritas que precisavam aumentar um arquivo falharam com `ENOSPC`, embora houvesse espaço de sobra no total. As 59 extensões que deram certo exigiram realocar o arquivo inteiro e copiar bloco a bloco (uma leitura e uma escrita por bloco), o que explica os 15 acessos e 78 ms por `write`. A contígua foi a mais lenta no total (85 s), apesar de ser a mais rápida por `read`.
- **Encadeada (o custo da corrente):** Não houve nenhuma falha, porque qualquer bloco livre serve. Mas cada `read` em posição aleatória precisou ler em média 75 blocos para seguir os ponteiros até o bloco pedido, e a primeira escrita depois de cada `open` em modo acréscimo percorreu o arquivo inteiro para chegar ao fim (143 acessos por `write`). O tempo foi menor do que esses números sugerem (6,4 ms por `read`) porque, num disco recém-formatado, os primeiros blocos livres costumam ser vizinhos, e ler blocos consecutivos não paga rotação no modelo.
- **FAT (o melhor dos dois mundos neste modelo):** Os mesmos blocos da encadeada, sem nenhum custo de corrente: 1,9 acesso por operação e o menor tempo total (9,9 s, 8,6 vezes menos que a contígua). A vantagem depende de a tabela estar em memória, o que o modelo assume de graça.
- **Indexada:** Sem fragmentação nem falhas, com acesso direto a custo fixo: cada `read` lê o índice antes do dado (6,1 acessos por `read` de ~3 blocos, porque arquivos grandes têm índice de 2 níveis). Cada leitura de índice é um acesso aleatório que paga rotação, e por isso o `read` custa 19 ms, mais que na encadeada, apesar de bem menos acessos. O `create` custa 7 acessos, porque grava os índices do arquivo e lê os índices dos diretórios. A indexada também usou mais espaço: 134 blocos livres a menos que a FAT no fim, que é o espaço dos índices.
- A hipótese se confirmou em todos os pontos. O único resultado inesperado foi a encadeada ficar mais rápida que a indexada no tempo total, apesar de 18 vezes mais acessos, o que mostra de novo que, num disco rígido, a ordem dos acessos pesa mais que a quantidade.

**Veredito:** CONFIRMADA

### X12 — Integração: cargas de arquivos → cache → escalonador

**Hipótese:** A alocação indexada deve multiplicar as requisições que chegam ao disco (as leituras de índice), e sem cache o tempo deve crescer na mesma proporção. Com a cache, as leituras de índice devem virar acertos, porque o mesmo bloco de índice é lido a cada acesso ao arquivo, e o custo extra da indexada deve quase desaparecer. Os escalonadores devem ajudar pouco no compilador, cujos acessos já são próximos, e mais no banco de dados, cujos acessos são espalhados.

**Fundamentação:** Silberschatz, seção 12.6: o desempenho do sistema de arquivos depende da alocação, da cache de blocos e da ordem dos acessos; a cache de blocos mantém em memória justamente os metadados mais usados, como índices e diretórios. Seção 12.4.3: o custo dos blocos de índice. Seção 10.4: escalonamento de disco.

**Configuração:** As cargas `compilador` e `banco_dados` do X3, rodadas com alocação contígua e indexada guardando o histórico de acessos; o histórico vira requisições de E/S (cada acesso de uma operação chega no instante da operação); FCFS, SSTF e SCAN; disco rígido; interrupção; sem cache e com cache LRU de 1.024 blocos em write-back.

**Resultados:**

| Carga e alocação | Requisições | Cache | Escalonador | Tempo total (ms) | Resposta média (ms) | Deslocamento | Acertos (%) | Escritas físicas |
|---|---:|---|---|---:|---:|---:|---:|---:|
| compilador + contígua | 5.400 | nenhuma | FCFS | 11.987 | 4.970,9 | 6.900 | — | 1.109 |
| compilador + contígua | 5.400 | nenhuma | SSTF | 9.988 | 5.170,1 | 10 | — | 1.109 |
| compilador + contígua | 5.400 | LRU | FCFS | 1.952 | 0,2 | 104 | 90,4 | 0 |
| compilador + indexada | 11.705 | nenhuma | FCFS | 32.045 | 14.961,0 | 10.772 | — | 2.014 |
| compilador + indexada | 11.705 | nenhuma | SSTF | 28.848 | 10.563,6 | 11 | — | 2.014 |
| compilador + indexada | 11.705 | LRU | FCFS | 1.952 | 0,2 | 116 | 95,7 | 0 |
| banco_dados + contígua | 3.610 | nenhuma | FCFS | 19.847 | 6.158,8 | 360.570 | — | 1.196 |
| banco_dados + contígua | 3.610 | nenhuma | SSTF | 15.415 | 4.106,2 | 1.518 | — | 1.196 |
| banco_dados + contígua | 3.610 | LRU | FCFS | 14.912 | 2.151,3 | 260.926 | 4,9 | 670 |
| banco_dados + contígua | 3.610 | LRU | SSTF | 12.991 | 1.411,9 | 2.697 | 4,8 | 670 |
| banco_dados + indexada | 10.314 | nenhuma | FCFS | 52.180 | 22.146,1 | 924.508 | — | 1.290 |
| banco_dados + indexada | 10.314 | nenhuma | SSTF | 42.512 | 17.353,2 | 257 | — | 1.290 |
| banco_dados + indexada | 10.314 | LRU | FCFS | 15.035 | 765,1 | 263.584 | 74,5 | 690 |
| banco_dados + indexada | 10.314 | LRU | SSTF | 13.086 | 509,5 | 2.541 | 74,6 | 690 |

As linhas do SCAN estão no CSV: sem cache, coincidem com as do SSTF; com cache, o SCAN teve resposta parecida, mas deslocamento bem maior (até 49.996 cilindros), por ir à borda com a fila quase vazia. Gráfico: `graficos/X12_resposta.png` (os rótulos do eixo horizontal do gráfico padrão se sobrepõem; a tabela acima traz os mesmos números).

**Evidências:** `resultados/es.csv` (linhas com experimento = X12); `graficos/X12_resposta.png`.

**Análise:**

- **Escala dos tempos:** As cargas de arquivos registram as operações em intervalos curtos, e todos os acessos de uma operação chegam juntos. Sem cache, o disco não acompanha, e as respostas médias chegam a segundos. Os valores absolutos refletem essa compressão; o que interessa é a comparação entre configurações.
- **O custo da indexada sem cache:** A indexada multiplicou as requisições por 2,2 no compilador e por 2,9 no banco de dados, e o tempo total (FCFS) por 2,7 e 2,6. As leituras de índice são acessos a blocos que não são vizinhos dos dados, então cada uma paga rotação. É o mesmo efeito do X11, agora visto na camada de baixo.
- **A cache anula o custo da indexada:** Com a cache LRU, a taxa de acertos do banco de dados com indexada foi de 74,5%, contra 4,9% com contígua. A diferença é toda das leituras de índice: o banco lê blocos aleatórios de uma tabela de 64 MiB (16.384 blocos, muito maior que a cache), e os dados quase nunca são reaproveitados, mas os 17 blocos de índice da tabela são lidos a cada acesso e ficam sempre na cache. Com isso, o tempo total da indexada caiu de 52.180 para 15.035 ms, praticamente igual ao da contígua com cache (14.912 ms). A resposta média da indexada com cache (765 ms) parece bem melhor que a da contígua (2.151 ms), mas isso é um efeito da média: as leituras de índice viraram milhares de requisições quase instantâneas que puxam a média para baixo. O tempo total, que mede o trabalho de verdade, é o mesmo.
- **Compilador com cache:** Com cache, 90% a 96% de acertos, e o tempo total cai para 1.952 ms, que é a duração da própria carga: o disco deixa de ser o gargalo. As escritas físicas aparecem como zero porque a carga termina antes da primeira sincronização (5 s), então todas as escritas ficaram sujas na cache. Numa queda de energia, todas se perderiam; a comparação de escritas físicas nesse caso não é justa com o write-back.
- **Escalonadores:** No compilador sem cache, o SSTF reduziu o deslocamento de 6.900 para 10 cilindros e o tempo total em 17%, mas a resposta média ficou até um pouco pior que no FCFS (5.170 contra 4.971 ms), porque favorece os pedidos próximos e deixa outros esperando. No banco de dados, o SSTF reduziu o tempo total em 22% sem cache (19.847 → 15.415 ms) e em 13% com cache. Como os acessos do banco ficam todos dentro da tabela (~256 cilindros), o ganho vem de ordenar pedidos próximos, e não de evitar buscas longas.
- **Veredito:** A hipótese se confirmou quanto à cache e ao custo da indexada. Quanto aos escalonadores, o ganho no banco de dados foi menor que o esperado, porque a busca é curta e o custo dominante é a rotação, que nenhum escalonador reduz.

**Veredito:** PARCIALMENTE CONFIRMADA

## 4. Relação com sistemas reais

**Escalonadores de disco (X1):** O Linux permite escolher o escalonador de cada dispositivo em tempo de execução, em `/sys/block/<dispositivo>/queue/scheduler`, entre `mq-deadline`, `bfq`, `kyber` e `none` (documentação do kernel, "Switching Scheduler"). Nenhum deles é o SSTF puro, justamente pelo risco de inanição que apareceu na carga concentrada. O `mq-deadline` combina as duas ideias do X1: em condições normais despacha em ordem de setor, como um elevador (SCAN), e cada pedido recebe um prazo (por padrão, 500 ms para leituras e 5 s para escritas); quando o mais antigo vence, ele é atendido primeiro, o que evita a inanição. O `bfq` divide o tempo do disco entre processos para dar justiça a aplicações interativas. Para SSDs e NVMe, distribuições como RHEL e SUSE usam `none` (sem reordenação), porque sem braço mecânico não há busca a otimizar, como mostrou o dispositivo rápido do X2. O defeito do SCAN observado na carga concentrada (idas desnecessárias até a borda) explica por que implementações reais usam variantes do tipo LOOK, que só vão até o último pedido. O resultado da carga sequencial também tem paralelo direto: o Linux junta pedidos vizinhos (*merging*) e faz leitura antecipada (*readahead*) para aproveitar justamente a ausência de busca e rotação entre blocos consecutivos.

**Polling × interrupção (X2):** O resultado do dispositivo rápido corresponde a uma mudança real dos sistemas operacionais. No Linux, o `io_uring` oferece o modo `IORING_SETUP_IOPOLL`, que faz espera ocupada pela conclusão em vez de receber uma interrupção; a própria documentação diz que isso reduz a latência à custa de mais CPU e que o modo serve para dispositivos que suportam polling, como os NVMe. Na rede, o mecanismo NAPI do Linux troca interrupções por polling quando o tráfego é alto. Para discos rígidos, todos os sistemas (Windows, Linux, macOS) usam interrupção com DMA, porque esperar ocupado por milissegundos desperdiçaria a CPU, como mostraram os 86% a 100% do polling no X2.

**Resolução de caminhos (X4):** Em sistemas reais, o custo de resolver caminhos profundos não chega ao disco na maior parte do tempo. O Linux mantém o *dcache* (cache de entradas de diretório), descrito na documentação do kernel ("Pathname lookup") como a estrutura que guarda informação sobre nomes para torná-los disponíveis rapidamente na busca; a resolução começa no modo RCU-walk, sem travas, enquanto o que procura estiver na cache. O Windows (NTFS) e o macOS (APFS) também mantêm caches de nomes e de metadados em memória. Por isso, no mundo real, a primeira abertura de um caminho profundo é cara e as seguintes quase não custam acesso ao disco, enquanto no simulador todo `open` relê todos os diretórios. Diretórios grandes também mudam o quadro: o ext4 usa índices em árvore (htree) e o NTFS usa árvores B+, em vez da busca num único bloco do modelo.

**Tabelas de arquivos abertos (X5):** O Linux implementa a mesma ideia de dois níveis, com três estruturas: a tabela de descritores de cada processo aponta para um `struct file` (uma por chamada a `open`, com a posição e o modo), que aponta para o `inode` em memória (um por arquivo, com contador de referências). A diferença em relação ao modelo do livro é que a posição fica no `struct file`, que pode ser compartilhado entre processos depois de um `fork`. O Windows usa uma tabela de *handles* por processo que aponta para objetos de arquivo do kernel, com contagem de referências. O comportamento do `unlink` de arquivo aberto implementado no N3 é o do UNIX (Linux e macOS): o nome some do diretório, mas os blocos só são liberados no último `close`. No Windows, por padrão, apagar um arquivo aberto falha ou fica pendente, conforme o modo de compartilhamento usado na abertura.

**Metadados gravados no close (X3):** O modelo grava o FCB sujo apenas no `close`. Sistemas reais vão além e adiam também os dados: o cache de páginas do Linux e o cache de arquivos do Windows mantêm blocos sujos em memória e os gravam periodicamente, e sistemas com journaling (ext4, NTFS) ou cópia na escrita (APFS) gravam metadados de forma a sobreviver a uma queda de energia.

**Cache de blocos e write-back (X6):** O Linux não tem uma cache de blocos separada: os dados de arquivos ficam no *page cache*, e as páginas sujas são gravadas por *threads* do kernel em segundo plano. Os parâmetros ficam em `/proc/sys/vm`: `dirty_writeback_centisecs` define de quanto em quanto tempo essas *threads* acordam, por padrão 500 centésimos de segundo (5 s, o mesmo intervalo do simulador), e `dirty_expire_centisecs` define a idade a partir da qual um dado sujo deve ser gravado, por padrão 30 s. O sistema real evita a rajada que apareceu no X6 de duas formas: grava só as páginas mais velhas que o limite a cada despertar, e limita a fração da memória que pode ficar suja (`dirty_background_ratio` e `dirty_ratio`, 10% e 20% por padrão), forçando a gravação antes de acumular demais. A perda numa queda de energia medida no X6 é o motivo de existirem `fsync` e os sistemas com journaling (ext4, NTFS): o journal grava os metadados de forma ordenada, para que o sistema de arquivos continue consistente depois da queda, embora dados recentes ainda possam se perder. Quanto à substituição, sistemas reais não usam LRU pura, que custa caro em cada acesso, e sim aproximações: o Linux mantém listas de páginas ativas e inativas, e o Windows usa conjuntos de trabalho com envelhecimento.

**Escalonamento avançado (X7):** O DEADLINE do simulador é uma simplificação do `mq-deadline`. No Linux, cada pedido recebe um prazo (500 ms para leituras e 5 s para escritas, por padrão), e o escalonador despacha em lotes ordenados por setor; antes de cada lote, verifica se o pedido mais antigo venceu e, se sim, começa por ele. O tamanho do lote (`fifo_batch`, 16 por padrão) controla a troca entre vazão e latência. Os resultados do X7 mostram a mesma limitação documentada do sistema real: o prazo não é uma garantia rígida, porque o pedido vencido só é atendido quando o lote atual termina. A diferença é que a ordem base do `mq-deadline` é uma varredura em ordem crescente de setor (um elevador de um só sentido, como o C-LOOK), e não o SSTF. Pelos resultados do X7, essa escolha faz sentido: o C-LOOK teve a menor espera máxima na carga mais pesada.

**Alocação em disco (X11):** A FAT do X11 é a dos pendrives e cartões de memória (FAT32, exFAT). Em sistemas reais, a tabela também fica no disco, e o sistema a mantém em cache; com volumes grandes, ela não cabe inteira na memória, e o acesso direto volta a custar leituras. A alocação indexada é a base dos *i-nodes* do Unix: o ext2 e o ext3 usam 12 ponteiros diretos e blocos de indireção simples, dupla e tripla, e, com blocos de 4 KiB, cada bloco de indireção guarda 1.024 ponteiros, o mesmo número do simulador. O ext4 trocou esse mapa por uma árvore de *extents*: em vez de um ponteiro por bloco, cada entrada descreve uma sequência contígua de blocos (início e comprimento). A documentação do kernel dá o exemplo de um trecho contíguo de 1.000 blocos, que exigia um bloco de indireção inteiro e passa a ser descrito por uma única entrada. É a combinação das vantagens que o X11 mostrou: o acesso barato da alocação contígua sem a fragmentação externa que fez a contígua falhar 113 vezes. O NTFS faz o mesmo com *runs* na MFT, e o APFS, com *extents* numa árvore B.

**Integração (X12):** O resultado de que a cache anula o custo dos blocos de índice corresponde ao comportamento real: no Linux, os metadados (blocos de índice, *extents*, diretórios) passam pelo mesmo *page cache* e pela cache de *inodes* e *dentries*, e um arquivo em uso tem seus metadados quase sempre em memória. O efeito da média de resposta no X12 também tem paralelo em ferramentas reais, como o `iostat`, em que muitas requisições pequenas atendidas da cache podem esconder a latência das que vão ao disco; por isso métricas como o percentil 95 e o tempo total são mais confiáveis que a média.

## 5. Limitações do simulador

**Sem cache:** No núcleo não há cache de blocos nem de diretórios. Todo `open` relê todos os diretórios do caminho, e toda leitura vai ao disco. Isso exagera o custo absoluto de metadados no X3 e no X4 em relação a um sistema real, onde essas leituras costumam ser servidas da memória.

**Diretórios contíguos:** No X4, os diretórios foram criados em sequência e ficaram em blocos vizinhos, o que fez a profundidade quase não pesar no tempo. Em um disco usado por muito tempo eles estariam espalhados, e a conclusão sobre o tempo seria outra.

**Latência rotacional fixa:** A rotação é sempre de meia volta (4,17 ms), exceto para o bloco seguinte. Discos reais têm latência variável, e as controladoras reordenam pedidos levando a rotação em conta (*Native Command Queuing*). No X1, isso limita o ganho possível dos escalonadores, porque 72% do serviço nas rajadas é rotação, que nenhum algoritmo do livro reduz.

**Um pedido por vez:** O disco atende um pedido de cada vez, sem fila interna, sem junção de pedidos vizinhos e sem leitura antecipada. No Linux, a junção de pedidos tornaria o FCFS da carga sequencial menos desastroso.

**Camada de arquivos sem fila:** O simulador de arquivos acessa o disco em ordem, sem escalonador e sem concorrência real entre processos. Os resultados do X3 a X5 não sofrem influência do escalonamento estudado no X1.

**Custo de CPU simplificado:** O modelo de CPU do X2 não inclui o custo de trocas de contexto adicionais, de cache de processador nem de agrupamento de interrupções (*interrupt coalescing*), que reduziria o custo da interrupção em dispositivos rápidos.

**Cache sem leitura antecipada e sem limite de sujos:** A cache do M1 não faz *readahead* nem limita a quantidade de blocos sujos, e a sincronização grava todos de uma vez. Por isso o write-back do X6 sofre com rajadas que o Linux evita.

**Integração sem tempo de processamento:** No X12, os acessos de cada operação chegam todos no mesmo instante, e as operações chegam no ritmo da carga, sem esperar a anterior terminar. Num sistema real, um processo só pede o próximo bloco depois de receber o anterior, e a fila nunca cresceria até segundos.

**FAT em memória de graça:** A FAT do M6 assume que toda a tabela está em memória, sem custo de leitura nem de gravação, o que favorece a FAT no X11.

**Cargas sintéticas:** As cargas têm 2.000 pedidos e padrões idealizados. Com elas, a vantagem de justiça do SCAN sobre o SSTF quase não apareceu; com cargas mais longas e mais pesadas, a inanição do SSTF seria mais visível.

## 6. Conclusões

1. Escalonar vale mais quanto maior a fila, e o maior ganho vem de evitar a rotação. Nas rajadas, SSTF e SCAN reduziram o deslocamento em 16 vezes; na carga sequencial, atender blocos consecutivos levou a resposta média de 10,2 s para 17 ms. O SCAN, que vai sempre até a borda, perdeu até para o FCFS na carga concentrada, o que justifica o LOOK e o C-LOOK; o DEADLINE manteve a média do SSTF e limitou a inanição, sem garantir o prazo de forma rígida, como o `mq-deadline` do Linux.

2. Polling ou interrupção depende da velocidade do dispositivo. A interrupção é muito melhor no disco rígido (1% contra 86% de CPU), e o polling passa a ser mais barato quando o dispositivo responde antes do custo de tratar uma interrupção, como nos SSDs NVMe.

3. Num disco rígido, a ordem dos acessos pesa mais que a quantidade. O banco de dados fez menos acessos que o compilador e levou 66% mais tempo; no X11, a encadeada fez 18 vezes mais acessos que a indexada e ainda assim terminou antes.

4. As duas tabelas de arquivos abertos separam o que é do arquivo do que é de cada abertura. A tabela global ficou com uma entrada por arquivo (12) enquanto havia o dobro de aberturas simultâneas (24), cada uma com sua própria posição.

5. A cache só ajuda quando há reuso, e o write-back troca segurança por desempenho. A LRU chegou a 67% de acertos e superou a FIFO nas capacidades pequenas; o write-back gravou 48% menos blocos, mas perdeu até 55 numa queda de energia e, sem limite de blocos sujos, piorou a resposta com as rajadas de sincronização.

6. A alocação define o custo das camadas de baixo, e a cache muda o quadro. A contígua falhou por fragmentação externa com 10% do disco livre, a encadeada pagou caro no acesso direto, e FAT e indexada resolveram os dois problemas. Na integração, o custo extra da indexada, que multiplicou o tempo por 2,6 sem cache, desapareceu com a cache, porque os blocos de índice são os mais reaproveitados.

## 7. Referências

- SILBERSCHATZ, A.; GALVIN, P. B.; GAGNE, G. *Operating System Concepts*. 9. ed. Wiley, 2013. Seções 10.1, 10.4, 11.1 a 11.3, 12.2 a 12.4, 12.6 e 13.2.
- LINUX KERNEL DOCUMENTATION. *Switching Scheduler*. https://www.kernel.org/doc/html/latest/block/switching-sched.html
- LINUX KERNEL DOCUMENTATION. *Deadline IO scheduler tunables*. https://www.kernel.org/doc/Documentation/block/deadline-iosched.rst
- LINUX KERNEL DOCUMENTATION. *Pathname lookup*. https://www.kernel.org/doc/html/latest/filesystems/path-lookup.html
- LINUX MAN-PAGES. *io_uring_setup(2)*, descrição de `IORING_SETUP_IOPOLL`. https://man7.org/linux/man-pages/man2/io_uring_setup.2.html
- SUSE. *Tuning I/O Performance* (escalonadores com blk-mq). https://documentation.suse.com/sles/12-SP5/html/SLES-all/cha-tuning-io.html
- LINUX KERNEL DOCUMENTATION. *Documentation for /proc/sys/vm* (`dirty_writeback_centisecs`, `dirty_expire_centisecs`). https://www.kernel.org/doc/Documentation/sysctl/vm.txt
- LINUX KERNEL DOCUMENTATION. *The Contents of inode.i_block* (ext4: mapa de blocos e árvore de extents). https://docs.kernel.org/filesystems/ext4/ifork.html
- KERNEL INTERNALS. *Page Cache Writeback* (valores padrão dos parâmetros de gravação). https://kernel-internals.org/io/page-cache-writeback/
- MÓR, F. N. Repositório da disciplina: código do SimES e roteiros das aulas de E/S. https://github.com/ProfessorFilipo/Aulas_SisOp

## 8. Declaração de autoria e uso de IA

**Quem fez o quê:** 

- Betina Borchardt Kusler: núcleo completo (N2: SSTF, SCAN, polling e interrupção; N3: sistema de arquivos inteiro, com caminhos, open/read/write/seek/close/unlink e tabelas de arquivos abertos), integração ponta a ponta, experimentos X1 a X5 e X12, junção e validação de todos os módulos, relatório geral (resumo, escopo, implementação, sistemas reais, limitações e conclusões).
- Gabriella Schmidt: M1 — cache de blocos (LRU e FIFO, write-through e write-back) → arquivo simes/es/cache.py → experimento X6.
- Lucas Goettert: escalonamento avançado (C-SCAN, LOOK, C-LOOK e DEADLINE) → classes CSCAN, LOOK, CLOOK e Deadline em simes/es/escalonadores.py → experimento X7.
- Lucas Marchese: alocação encadeada, FAT e indexada → classes AlocadorEncadeado, AlocadorFAT e AlocadorIndexado em simes/arquivos/alocacao.py → experimento X11.

- Todos os integrantes realizaram suas funções com auxílio de IA.

**Uso de ferramentas de IA:**

| Ferramenta | Finalidade | Onde foi usada (arquivos ou seções) |
|---|---|---|
| Claude (Anthropic) | Auxílio guiado utilizando a IA como "tutora" para implementação do núcleo (N2 e N3), dos módulos M1, M2 e M6 e da integração; execução dos experimentos X1 a X7, X11 e X12 e das medições de apoio do X1; pesquisa e explicações das fontes sobre Linux; estruturação inicial do relatório. Os resultados foram conferidos pelos testes automáticos e pela validadora da entrega | `simes/es/escalonadores.py`, `simes/es/cpu.py`, `simes/es/cache.py`, `simes/arquivos/sistema.py`, `simes/arquivos/alocacao.py`, `simes/integracao.py`, `grupo.json` e as seções 0 a 8 deste relatório |
