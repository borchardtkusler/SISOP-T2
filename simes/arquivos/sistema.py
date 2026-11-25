# -*- coding: utf-8 -*-
"""
Sistema de arquivos simulado (camada 3).

Referência: Silberschatz, 9ª ed., cap. 11 — operações, FCB, tabelas de arquivos abertos,
métodos de acesso, estrutura de diretórios, links e proteção.

O que já vem pronto (FORNECIDO): a criação da raiz, as tabelas e os métodos auxiliares
(nome começando com _). Implementem os métodos marcados com TODO.

=====================================================================================
REGRAS DE CUSTO (iguais para todos os grupos — sigam à risca)
=====================================================================================
Um acesso = um bloco lido ou gravado (use _ler, _escrever e _aplicar; eles contam tudo).

Diretórios: cada diretório ocupa 1 bloco (o bloco 0 do diretório, obtido com
_bloco_do_diretorio). Ler um diretório = 1 leitura desse bloco.

resolver("/a/b/c")   lê os diretórios "/", "/a" e "/a/b" (3 leituras) e devolve o FCB de c.
                     resolver("/") devolve a raiz sem ler nada.
Operações que criam, removem ou alteram uma entrada leem os diretórios do caminho até o
pai (inclusive), exatamente como resolver, e depois:

mkdir(p)             + aloca 1 bloco para o novo diretório, grava o bloco do novo diretório
                       (1 escrita) e o bloco do pai (1 escrita)
create(p, tamanho)   + aloca ceil(tamanho / TAMANHO_BLOCO) blocos (conteúdo não é gravado)
                       e grava o bloco do pai (1 escrita)
open(p, modo, h)     lê os diretórios como resolver; nenhuma escrita
read(h, n)           lê os blocos que contêm os bytes [posição, posição + n), limitados ao
                     tamanho do arquivo; avança a posição; devolve os bytes lidos
write(h, n)          se precisar, estende o arquivo (alocador.estender); grava os blocos que
                     contêm [posição, posição + n); avança a posição; atualiza o tamanho e
                     marca o FCB como sujo. No modo 'a', a escrita começa no fim do arquivo.
seek(h, posicao)     muda a posição; nenhum acesso
close(h)             se o FCB está sujo, grava o bloco do diretório pai (1 escrita) e limpa
                     o "sujo"; atualiza as tabelas
unlink(p)            + grava o bloco do pai (1 escrita). Se o arquivo ficar sem links e
                     ninguém o tiver aberto, libera os blocos; se estiver aberto, a liberação
                     acontece no último close.

Tabelas de arquivos abertos:
- self.tabela_global: dict fcb_id -> EntradaGlobal. Uma entrada por arquivo aberto; o
  contador soma as aberturas de todos os processos. A entrada sai quando o contador zera.
- self.tabelas_processo: dict processo -> {handle: EntradaProcesso}. Uma entrada por
  abertura, com a posição e o modo.

Modos de abertura: 'r' (só leitura), 'w' (só escrita), 'rw' (ambos), 'a' (acréscimo, só
escrita). Ler com um handle sem 'r', ou escrever sem 'w'/'a': ErroSA('EBADF').
Erros: lancem ErroSA com o código adequado (veja estruturas.py).

Ganchos dos módulos (já chamados pelas operações do núcleo, que vocês implementam):
- _verificar_permissao(processo, fcb, modo): no núcleo não faz nada; o M5 implementa.
- _verificar_trava(processo, fcb):            no núcleo não faz nada; o M5 implementa.
  O núcleo deve chamar _verificar_permissao no open e _verificar_trava no read e no write.
"""
import math
from collections import Counter

from simes import parametros as P
from simes.arquivos.estruturas import FCB, EntradaGlobal, EntradaProcesso, ErroSA

MAX_LINKS_SIMBOLICOS = 8


class SistemaArquivos:

    def __init__(self, camada, alocador, bloqueio="consultivo"):
        self.camada = camada
        self.alocador = alocador
        self.bloqueio = bloqueio            # 'consultivo' ou 'mandatorio' (M5)
        self.fcbs = {}
        self._proximo_id = 0
        self.agora_ms = 0.0                 # atualizado pelo simulador antes de cada operação
        self.tabela_global = {}             # fcb_id -> EntradaGlobal
        self.tabelas_processo = {}          # processo -> {handle: EntradaProcesso}
        self.usuarios = {}                  # processo -> nome do usuário (M5); padrão: 'root'
        self.contadores = Counter()         # indicadores extras dos módulos (vão para o CSV)
        self.raiz = self._novo_fcb("/", "diretorio", None)
        self.alocador.alocar(self.raiz, 1)  # a raiz já existe ao "formatar": sem custo

    # ================================================================ FORNECIDO
    def _novo_fcb(self, nome, tipo, pai, processo=None):
        """Cria um FCB (dono = usuário do processo) e o registra em self.fcbs. Não aloca blocos."""
        fcb = FCB(self._proximo_id, nome, tipo, pai, self.agora_ms, self.usuario_de(processo))
        self.fcbs[fcb.id] = fcb
        self._proximo_id += 1
        return fcb

    def usuario_de(self, processo):
        return self.usuarios.get(processo, "root")

    def _ler(self, blocos):
        self.camada.ler(blocos)

    def _escrever(self, blocos):
        self.camada.escrever(blocos)

    def _aplicar(self, extras):
        """Executa a lista de acessos extras devolvida pelo alocador."""
        for tipo, bloco in extras:
            if tipo == "L":
                self._ler([bloco])
            else:
                self._escrever([bloco])

    def _bloco_do_diretorio(self, diretorio):
        """Bloco físico onde está o conteúdo do diretório (já executa os extras do alocador)."""
        bloco, extras = self.alocador.bloco_fisico(diretorio, 0)
        self._aplicar(extras)
        return bloco

    def _ler_diretorio(self, diretorio):
        self._ler([self._bloco_do_diretorio(diretorio)])

    def _gravar_diretorio(self, diretorio):
        self._escrever([self._bloco_do_diretorio(diretorio)])

    def _blocos_do_intervalo(self, fcb, inicio, fim):
        """Blocos físicos que contêm os bytes [inicio, fim) do arquivo (executa os extras)."""
        if fim <= inicio:
            return []
        primeiro = inicio // P.TAMANHO_BLOCO
        ultimo = (fim - 1) // P.TAMANHO_BLOCO
        blocos = []
        for i in range(primeiro, ultimo + 1):
            bloco, extras = self.alocador.bloco_fisico(fcb, i)
            self._aplicar(extras)
            blocos.append(bloco)
        return blocos

    @staticmethod
    def _blocos_necessarios(tamanho):
        return int(math.ceil(tamanho / float(P.TAMANHO_BLOCO)))

    @staticmethod
    def _dividir(caminho):
        if not caminho.startswith("/"):
            raise ErroSA("EINVAL", "o caminho deve ser absoluto: %s" % caminho)
        return [p for p in caminho.split("/") if p]

    def _entrada(self, processo, handle):
        try:
            return self.tabelas_processo[processo][handle]
        except KeyError:
            raise ErroSA("EBADF", "%s não tem o handle %s" % (processo, handle))

    def _liberar_arquivo(self, fcb):
        self.alocador.liberar(fcb)
        del self.fcbs[fcb.id]

    def _verificar_permissao(self, processo, fcb, modo):
        """Gancho do M5. No núcleo, tudo é permitido."""
        return None

    def _verificar_trava(self, processo, fcb):
        """Gancho do M5. No núcleo, travas não existem."""
        return None

    # ===================================================================== núcleo (N3)
    MODOS = ("r", "w", "rw", "a")

    def resolver(self, caminho, seguir_simbolico=True):
        """Devolve o FCB do caminho absoluto, lendo os diretórios do caminho (ver regras).
        Erros: ENOENT, ENOTDIR. (Links simbólicos são do módulo M4, que não faz parte deste
        trabalho; o parâmetro seguir_simbolico é mantido só por compatibilidade.)"""
        atual = self.raiz
        for nome in self._dividir(caminho):
            # Só se desce por diretórios: um arquivo no meio do caminho é ENOTDIR.
            if atual.tipo != "diretorio":
                raise ErroSA("ENOTDIR", "%s não é diretório" % atual.nome)
            self._ler_diretorio(atual)                 # 1 leitura por diretório percorrido
            if nome not in atual.entradas:
                raise ErroSA("ENOENT", "%s não existe" % caminho)
            atual = self.fcbs[atual.entradas[nome]]
        return atual

    def _pai_e_nome(self, caminho):
        """Lê os diretórios do caminho até o PAI (inclusive), exatamente como o resolver
        leria para chegar ao último componente, e devolve (fcb_do_pai, nome)."""
        partes = self._dividir(caminho)
        if not partes:
            raise ErroSA("EEXIST", "a raiz já existe")
        pai = self.resolver("/" + "/".join(partes[:-1]))   # lê até o avô
        if pai.tipo != "diretorio":
            raise ErroSA("ENOTDIR", "%s não é diretório" % pai.nome)
        self._ler_diretorio(pai)                             # + 1 leitura: o próprio pai
        return pai, partes[-1]

    def mkdir(self, processo, caminho):
        pai, nome = self._pai_e_nome(caminho)
        if nome in pai.entradas:
            raise ErroSA("EEXIST", "%s já existe" % caminho)
        novo = self._novo_fcb(nome, "diretorio", pai.id, processo)
        try:
            self._aplicar(self.alocador.alocar(novo, 1))
        except ErroSA:
            del self.fcbs[novo.id]                           # não deixa FCB órfão
            raise
        pai.entradas[nome] = novo.id
        self._gravar_diretorio(novo)                         # 1 escrita: bloco do novo diretório
        self._gravar_diretorio(pai)                          # 1 escrita: entrada nova no pai

    def create(self, processo, caminho, tamanho):
        if tamanho < 0:
            raise ErroSA("EINVAL", "tamanho negativo")
        pai, nome = self._pai_e_nome(caminho)
        if nome in pai.entradas:
            raise ErroSA("EEXIST", "%s já existe" % caminho)
        novo = self._novo_fcb(nome, "arquivo", pai.id, processo)
        try:
            # Reserva os blocos; o conteúdo não é gravado (só os extras do alocador, se houver).
            self._aplicar(self.alocador.alocar(novo, self._blocos_necessarios(tamanho)))
        except ErroSA:
            del self.fcbs[novo.id]
            raise
        novo.tamanho = tamanho
        pai.entradas[nome] = novo.id
        self._gravar_diretorio(pai)                          # 1 escrita: entrada nova no pai

    def open(self, processo, caminho, modo, handle):
        if modo not in self.MODOS:
            raise ErroSA("EINVAL", "modo inválido: %s" % modo)
        fcb = self.resolver(caminho)                         # só leituras de diretório
        if fcb.tipo == "diretorio":
            raise ErroSA("EISDIR", "%s é diretório" % caminho)
        self._verificar_permissao(processo, fcb, modo)
        tabela = self.tabelas_processo.setdefault(processo, {})
        if handle in tabela:
            raise ErroSA("EINVAL", "%s já usa o handle %s" % (processo, handle))
        # Tabela global: uma entrada por arquivo aberto, com contador de aberturas.
        entrada = self.tabela_global.get(fcb.id)
        if entrada is None:
            entrada = self.tabela_global[fcb.id] = EntradaGlobal(fcb.id)
        entrada.contador += 1
        # Tabela do processo: uma entrada por abertura, com posição e modo próprios.
        tabela[handle] = EntradaProcesso(fcb.id, modo, 0)

    def read(self, processo, handle, n):
        entrada = self._entrada(processo, handle)
        if "r" not in entrada.modo:
            raise ErroSA("EBADF", "%s não foi aberto para leitura" % handle)
        if n < 0:
            raise ErroSA("EINVAL", "quantidade negativa")
        fcb = self.fcbs[entrada.fcb_id]
        self._verificar_trava(processo, fcb)
        inicio = entrada.posicao
        fim = min(inicio + n, fcb.tamanho)                  # não lê além do fim do arquivo
        if fim <= inicio:
            return 0
        self._ler(self._blocos_do_intervalo(fcb, inicio, fim))
        entrada.posicao = fim
        return fim - inicio

    def write(self, processo, handle, n):
        entrada = self._entrada(processo, handle)
        if entrada.modo not in ("w", "rw", "a"):
            raise ErroSA("EBADF", "%s não foi aberto para escrita" % handle)
        if n < 0:
            raise ErroSA("EINVAL", "quantidade negativa")
        fcb = self.fcbs[entrada.fcb_id]
        self._verificar_trava(processo, fcb)
        if entrada.modo == "a":
            entrada.posicao = fcb.tamanho                    # acréscimo: sempre no fim
        if n == 0:
            return 0
        inicio, fim = entrada.posicao, entrada.posicao + n
        faltam = self._blocos_necessarios(fim) - len(fcb.blocos)
        if faltam > 0:
            self._aplicar(self.alocador.estender(fcb, faltam))   # pode realocar (cópias)
        self._escrever(self._blocos_do_intervalo(fcb, inicio, fim))
        entrada.posicao = fim
        fcb.tamanho = max(fcb.tamanho, fim)
        fcb.modificado_ms = self.agora_ms
        fcb.sujo = True                                      # metadados gravados só no close
        return n

    def seek(self, processo, handle, posicao):
        entrada = self._entrada(processo, handle)
        if posicao < 0:
            raise ErroSA("EINVAL", "posição negativa")
        entrada.posicao = posicao                            # nenhum acesso ao disco

    def close(self, processo, handle):
        entrada = self._entrada(processo, handle)
        fcb = self.fcbs[entrada.fcb_id]
        if fcb.sujo:
            pai = self.fcbs.get(fcb.pai)
            if pai is not None:
                self._gravar_diretorio(pai)                  # 1 escrita: atualiza o FCB no pai
            fcb.sujo = False
        del self.tabelas_processo[processo][handle]
        global_ = self.tabela_global[fcb.id]
        global_.contador -= 1
        if global_.trava == processo:                        # (M5) o dono solta a trava
            global_.trava = None
        if global_.contador == 0:
            del self.tabela_global[fcb.id]
            if fcb.links == 0:
                self._liberar_arquivo(fcb)                   # último close de um arquivo removido

    def unlink(self, processo, caminho):
        pai, nome = self._pai_e_nome(caminho)
        if nome not in pai.entradas:
            raise ErroSA("ENOENT", "%s não existe" % caminho)
        fcb = self.fcbs[pai.entradas[nome]]
        if fcb.tipo == "diretorio":
            raise ErroSA("EISDIR", "%s é diretório" % caminho)
        del pai.entradas[nome]
        fcb.links -= 1
        self._gravar_diretorio(pai)                          # 1 escrita: entrada removida
        if fcb.links == 0 and fcb.id not in self.tabela_global:
            self._liberar_arquivo(fcb)                       # ninguém tem aberto: libera já

    # ======================================================== TODO — módulo M4
    def link(self, processo, existente, novo):
        """Hard link: lê os diretórios até `existente` (como resolver) e até o pai de `novo`;
        cria a entrada; links += 1; grava o bloco do pai de `novo` (1 escrita).
        Hard link para diretório: ErroSA('EPERM')."""
        raise NotImplementedError("TODO (M4): link")

    def symlink(self, processo, alvo, caminho):
        """Link simbólico: lê os diretórios até o pai de `caminho`; cria um FCB do tipo
        'simbolico' com fcb.alvo = alvo (sem blocos de dados); grava o bloco do pai (1 escrita).
        O alvo não precisa existir."""
        raise NotImplementedError("TODO (M4): symlink")

    def percorrer(self, processo, caminho):
        """Percorre a árvore a partir de `caminho` (como um `find`), lendo cada diretório
        visitado (1 leitura) e seguindo links simbólicos para diretórios. Não pode entrar em
        laço: ao chegar de novo a um diretório já visitado nesta travessia, conte
        self.contadores['ciclos_detectados'] e não desça. Contem também
        'percorrer_diretorios', 'percorrer_arquivos' e 'links_pendentes' (links simbólicos
        cujo alvo não existe; contem também os encontrados pelo open)."""
        raise NotImplementedError("TODO (M4): percorrer")

    # ======================================================== TODO — módulo M5
    # Regras do M5 (implementem também os ganchos _verificar_permissao e _verificar_trava,
    # sobrescrevendo-os aqui ou numa subclasse):
    #
    # _verificar_permissao(processo, fcb, modo) — chamado no open. Permissão exigida:
    #   'r' para o modo 'r'; 'w' para 'w' e 'a'; 'r' e 'w' para 'rw'.
    #   - usuário root: sempre permitido (conte 1 em contadores['verificacoes']);
    #   - se a ACL do arquivo tem uma entrada para o usuário, vale a PRIMEIRA entrada dele
    #     (some em 'verificacoes' a posição da entrada na lista, começando em 1);
    #   - senão, valem os bits: os do dono, se o usuário for o dono; senão, os de "outros"
    #     (grupos não são simulados). Some len(acl) + 1 em 'verificacoes';
    #   - negado: some 1 em contadores['negados'] e lance ErroSA('EACCES').
    #
    # _verificar_trava(processo, fcb) — chamado no read e no write. Se outro processo
    #   detém a trava do arquivo:
    #   - bloqueio 'consultivo': a operação segue; some 1 em 'violacoes_consultivo';
    #   - bloqueio 'mandatorio': some 1 em 'bloqueados_mandatorio' e lance ErroSA('EBUSY').
    # O close libera a trava se o processo que fecha for o dono dela.
    def usuario(self, processo, nome):
        """Associa o processo a um usuário (nenhum acesso ao disco)."""
        raise NotImplementedError("TODO (M5): usuario")

    def chmod(self, processo, caminho, permissoes):
        """Lê os diretórios até o arquivo; só o dono ou root (senão EPERM); grava o bloco do
        pai (1 escrita). permissoes em octal, como texto (ex.: '640')."""
        raise NotImplementedError("TODO (M5): chmod")

    def setacl(self, processo, caminho, usuario, permissoes):
        """Como o chmod, mas acrescenta (ou substitui) a entrada (usuario, 'rwx') na ACL."""
        raise NotImplementedError("TODO (M5): setacl")

    def lock(self, processo, handle):
        """Trava exclusiva do arquivo inteiro. Se outro processo detém a trava: EBUSY
        (conte 'travas_negadas'); senão conte 'travas_concedidas'."""
        raise NotImplementedError("TODO (M5): lock")

    def unlock(self, processo, handle):
        raise NotImplementedError("TODO (M5): unlock")
