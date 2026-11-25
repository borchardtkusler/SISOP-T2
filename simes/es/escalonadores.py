# -*- coding: utf-8 -*-
"""
Escalonadores de requisições de disco.

FCFS é FORNECIDO como exemplo. Implementem:
    núcleo (N2): SSTF e SCAN
    módulo M2:   C-SCAN, LOOK, C-LOOK e DEADLINE

Referência: Silberschatz, 9ª ed., seção 10.4 (Disk Scheduling) — pesquisa.

INTERFACE — todo escalonador implementa:

    escolher(fila, cabeca, direcao, agora, max_cilindro) -> (indice, nova_direcao, passar_por)

    fila          lista de Requisicao pendentes, na ordem de chegada (índice 0 = a mais antiga)
    cabeca        cilindro em que o braço está agora
    direcao       +1 (rumo aos cilindros maiores) ou -1 (rumo ao cilindro 0)
    agora         instante atual da simulação, em ms (usado pelo DEADLINE)
    max_cilindro  último cilindro do disco
    indice        posição, em `fila`, da requisição escolhida
    nova_direcao  direção do braço depois da escolha
    passar_por    lista de cilindros que o braço precisa visitar ANTES de ir à requisição
                  escolhida (ex.: o SCAN vai até a borda do disco antes de inverter).
                  Use [] quando o braço vai direto.

Regras comuns (para que todos os grupos obtenham os mesmos números):
- Requisição no mesmo cilindro da cabeça conta como "à frente" em qualquer direção.
- Empate (mesma distância): vence a que está antes na fila (chegou antes).
"""


class Escalonador:
    nome = "?"

    def escolher(self, fila, cabeca, direcao, agora, max_cilindro):
        raise NotImplementedError


class FCFS(Escalonador):
    """First-Come, First-Served: atende na ordem de chegada. FORNECIDO."""
    nome = "FCFS"

    def escolher(self, fila, cabeca, direcao, agora, max_cilindro):
        return 0, direcao, []


def _mais_proxima_a_frente(fila, cabeca, direcao):
    """Índice da requisição mais próxima da cabeça entre as que estão "à frente" na direção
    dada (o mesmo cilindro da cabeça conta como à frente). Empate: a que chegou antes.
    Devolve None se não houver nenhuma à frente."""
    melhor, melhor_dist = None, None
    for i, r in enumerate(fila):
        delta = r.cilindro - cabeca
        if delta * direcao < 0:          # está atrás da cabeça
            continue
        dist = abs(delta)
        if melhor is None or dist < melhor_dist:   # "<" estrito preserva a ordem de chegada
            melhor, melhor_dist = i, dist
    return melhor


# ---------------------------------------------------------------- núcleo (N2)
class SSTF(Escalonador):
    """
    Shortest Seek Time First: escolhe a requisição de menor distância até a cabeça.
    A direção devolvida é a do movimento feito (+1 se o alvo está acima, -1 se abaixo;
    mantém a direção atual se o alvo está no mesmo cilindro).
    """
    nome = "SSTF"

    def escolher(self, fila, cabeca, direcao, agora, max_cilindro):
        # Menor distância até a cabeça; em caso de empate, vence a de menor índice
        # (chegou antes), porque min() devolve o primeiro mínimo encontrado.
        indice = min(range(len(fila)), key=lambda i: abs(fila[i].cilindro - cabeca))
        alvo = fila[indice].cilindro
        if alvo > cabeca:
            direcao = +1
        elif alvo < cabeca:
            direcao = -1
        # alvo == cabeca: mantém a direção atual
        return indice, direcao, []


class SCAN(Escalonador):
    """
    SCAN (elevador): atende, na direção atual, a requisição mais próxima. Se não houver
    nenhuma à frente, o braço vai até a BORDA do disco (cilindro 0 ou max_cilindro, conforme a
    direção), inverte e atende a mais próxima na nova direção. A ida até a borda entra em
    `passar_por`.
    """
    nome = "SCAN"

    def escolher(self, fila, cabeca, direcao, agora, max_cilindro):
        indice = _mais_proxima_a_frente(fila, cabeca, direcao)
        if indice is not None:
            return indice, direcao, []
        # Nada à frente: o braço vai até a borda na direção atual e inverte.
        borda = max_cilindro if direcao > 0 else 0
        direcao = -direcao
        # Se a cabeça já está na borda, não há movimento a fazer até ela.
        passar_por = [borda] if borda != cabeca else []
        indice = _mais_proxima_a_frente(fila, borda, direcao)
        return indice, direcao, passar_por


# ------------------------------------------------------------------ módulo M2
class CSCAN(Escalonador):
    """
    C-SCAN: atende apenas subindo (direção +1). Sem requisições à frente, o braço vai até
    max_cilindro, volta ao cilindro 0 (o retorno CONTA como deslocamento) e continua subindo.
    """
    nome = "C-SCAN"

    def escolher(self, fila, cabeca, direcao, agora, max_cilindro):
        indice = _mais_proxima_a_frente(fila, cabeca, +1)
        if indice is not None:
            return indice, +1, []
        # Nada acima: sobe até a borda, volta ao cilindro 0 (o retorno conta) e segue subindo.
        passar_por = ([max_cilindro] if cabeca != max_cilindro else []) + [0]
        return _mais_proxima_a_frente(fila, 0, +1), +1, passar_por


class LOOK(Escalonador):
    """LOOK: como o SCAN, mas inverte na última requisição da direção, sem ir até a borda."""
    nome = "LOOK"

    def escolher(self, fila, cabeca, direcao, agora, max_cilindro):
        indice = _mais_proxima_a_frente(fila, cabeca, direcao)
        if indice is not None:
            return indice, direcao, []
        # Nada à frente: inverte aqui mesmo, na última requisição atendida, sem ir à borda.
        direcao = -direcao
        return _mais_proxima_a_frente(fila, cabeca, direcao), direcao, []


class CLOOK(Escalonador):
    """
    C-LOOK: atende apenas subindo; sem requisições à frente, o braço salta direto para a
    requisição de MENOR cilindro (o salto conta como deslocamento) e continua subindo.
    """
    nome = "C-LOOK"

    def escolher(self, fila, cabeca, direcao, agora, max_cilindro):
        indice = _mais_proxima_a_frente(fila, cabeca, +1)
        if indice is not None:
            return indice, +1, []
        # Nada acima: salta direto para a requisição de menor cilindro (empate: a mais antiga).
        indice = min(range(len(fila)), key=lambda i: fila[i].cilindro)
        return indice, +1, []


class Deadline(Escalonador):
    """
    DEADLINE (inspirado no mq-deadline do Linux): cada requisição tem um prazo
    (req.prazo = chegada + PRAZO_LEITURA_MS ou PRAZO_ESCRITA_MS). Se alguma requisição da
    fila já venceu o prazo (agora >= req.prazo), atende a de prazo mais antigo (empate: a que
    está antes na fila), mantendo a direção. Caso contrário, comporta-se como o SSTF.
    Objetivo: manter o bom desempenho médio do SSTF sem deixar requisições distantes
    esperando indefinidamente (inanição).
    """
    nome = "DEADLINE"

    def __init__(self):
        self._sstf = SSTF()

    def escolher(self, fila, cabeca, direcao, agora, max_cilindro):
        vencidas = [i for i, r in enumerate(fila) if agora >= r.prazo]
        if vencidas:
            # Prazo vencido: atende a de prazo mais antigo (min() pega a primeira no empate).
            indice = min(vencidas, key=lambda i: fila[i].prazo)
            return indice, direcao, []
        return self._sstf.escolher(fila, cabeca, direcao, agora, max_cilindro)


ESCALONADORES = {c.nome: c for c in (FCFS, SSTF, SCAN, CSCAN, LOOK, CLOOK, Deadline)}


def criar_escalonador(nome):
    try:
        return ESCALONADORES[nome]()
    except KeyError:
        raise ValueError("escalonador desconhecido: %s (opções: %s)" % (nome, ", ".join(ESCALONADORES)))


# ------------------------------------------------------------------ utilitário
def percorrer(escalonador, cilindros, cabeca, direcao=+1, max_cilindro=199):
    """
    Atende uma fila estática (todas as requisições chegam juntas) e devolve
    (ordem_dos_cilindros_atendidos, deslocamento_total). Útil para conferir os exemplos
    do livro, por exemplo: fila 98,183,37,122,14,124,65,67, cabeça em 53, disco 0..199.
    """
    from simes.es.requisicao import Requisicao
    from simes import parametros as P
    fila = [Requisicao(i, 0.0, "P1", "L", c * P.BLOCOS_POR_CILINDRO) for i, c in enumerate(cilindros)]
    ordem, total = [], 0
    while fila:
        i, direcao, passar = escalonador.escolher(fila, cabeca, direcao, 0.0, max_cilindro)
        for c in passar:
            total += abs(c - cabeca)
            cabeca = c
        r = fila.pop(i)
        total += abs(r.cilindro - cabeca)
        cabeca = r.cilindro
        ordem.append(r.cilindro)
    return ordem, total
