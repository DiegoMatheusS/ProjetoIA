import {
  BadRequestException,
  ConflictException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import {
  GrupoCategoriaProduto,
  StatusOferta,
  TipoProduto,
} from '../generated/prisma/enums';
import { PrismaService } from '../prisma/prisma.service';
import { AtualizarOfertaDto } from './dtos/atualizar-oferta.dto';
import { AtualizarParceiroDto } from './dtos/atualizar-parceiro.dto';
import { CriarOfertaDto } from './dtos/criar-oferta.dto';
import { CriarParceiroDto } from './dtos/criar-parceiro.dto';
import { VerificadorPrecosOfertasService } from './verificador-precos-ofertas.service';

@Injectable()
export class OfertasService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly verificadorPrecos: VerificadorPrecosOfertasService,
  ) {}

  private criarSlug(texto: string): string {
    return (
      texto
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-+|-+$/g, '') || 'parceiro'
    );
  }

  private calcularPercentualDesconto(
    precoAtual: unknown,
    precoAnterior: unknown,
  ): number | null {
    if (precoAnterior === null || precoAnterior === undefined) return null;

    const atual = Number(precoAtual);
    const anterior = Number(precoAnterior);
    if (
      !Number.isFinite(atual) ||
      !Number.isFinite(anterior) ||
      anterior <= 0 ||
      anterior <= atual
    ) {
      return null;
    }

    return Number((((anterior - atual) / anterior) * 100).toFixed(2));
  }

  private calcularVariacaoPercentual(
    precoSalvo: number,
    precoEncontrado: number,
  ): number {
    if (precoSalvo <= 0 || !Number.isFinite(precoSalvo)) return 100;
    return Number(
      ((Math.abs(precoEncontrado - precoSalvo) / precoSalvo) * 100).toFixed(2),
    );
  }

  private variacaoPrecoExigeRevisao(
    precoSalvo: number,
    precoEncontrado: number,
  ): { revisar: boolean; variacaoPercentual: number } {
    const variacaoPercentual = this.calcularVariacaoPercentual(
      precoSalvo,
      precoEncontrado,
    );

    return {
      revisar: variacaoPercentual > 35,
      variacaoPercentual,
    };
  }

  private grupoDestaqueProduto(produto: {
    tipo: TipoProduto;
    categoria: { slug: string; grupo: GrupoCategoriaProduto };
  }): 'HARDWARE' | 'PERIFERICOS' | 'MONITORES' | 'NOTEBOOKS' | 'SETUP' | null {
    if (
      produto.tipo === TipoProduto.NOTEBOOK ||
      produto.categoria.slug === 'notebooks'
    ) {
      return 'NOTEBOOKS';
    }

    if (produto.categoria.slug === 'monitores') return 'MONITORES';
    if (produto.categoria.grupo === GrupoCategoriaProduto.COMPONENTES) {
      return 'HARDWARE';
    }
    if (produto.categoria.grupo === GrupoCategoriaProduto.PERIFERICOS) {
      return 'PERIFERICOS';
    }
    if (produto.categoria.grupo === GrupoCategoriaProduto.SETUP) return 'SETUP';

    return null;
  }

  async criarParceiro(dados: CriarParceiroDto) {
    const nome = dados.nome.trim();
    const slug = this.criarSlug(nome);
    const dominio = dados.dominio?.trim().toLowerCase() || null;

    const existente = await this.prisma.parceiro.findUnique({
      where: { slug },
      select: { id: true },
    });
    if (existente) {
      throw new ConflictException(
        `Já existe um parceiro com o nome "${nome}".`,
      );
    }

    if (dominio) {
      const domExistente = await this.prisma.parceiro.findUnique({
        where: { dominio },
        select: { id: true },
      });
      if (domExistente) {
        throw new ConflictException(
          `Já existe um parceiro com o domínio "${dominio}".`,
        );
      }
    }

    return this.prisma.parceiro.create({
      data: {
        nome,
        slug,
        logoUrl: dados.logoUrl?.trim() || null,
        site: dados.site?.trim() || null,
        dominio,
        programaAfiliados: dados.programaAfiliados ?? false,
        observacao: dados.observacao?.trim() || null,
      },
    });
  }

  async listarParceirosPublicos() {
    const parceiros = await this.prisma.parceiro.findMany({
      where: { ativo: true },
      orderBy: { nome: 'asc' },
      select: {
        id: true,
        nome: true,
        slug: true,
        logoUrl: true,
        site: true,
        dominio: true,
        programaAfiliados: true,
      },
    });
    return { total: parceiros.length, parceiros };
  }

  async listarParceiros() {
    const parceiros = await this.prisma.parceiro.findMany({
      orderBy: { nome: 'asc' },
      select: {
        id: true,
        nome: true,
        slug: true,
        logoUrl: true,
        site: true,
        dominio: true,
        programaAfiliados: true,
        ativo: true,
        _count: { select: { ofertas: true } },
      },
    });
    return { total: parceiros.length, parceiros };
  }

  async buscarParceiro(id: number) {
    const parceiro = await this.prisma.parceiro.findUnique({
      where: { id },
      include: { _count: { select: { ofertas: true } } },
    });
    if (!parceiro) throw new NotFoundException('Parceiro não encontrado.');
    return parceiro;
  }

  async atualizarParceiro(id: number, dados: AtualizarParceiroDto) {
    const parceiro = await this.prisma.parceiro.findUnique({
      where: { id },
      select: { id: true },
    });
    if (!parceiro) throw new NotFoundException('Parceiro não encontrado.');

    let nome: string | undefined;
    let slug: string | undefined;
    if (dados.nome !== undefined) {
      nome = dados.nome.trim();
      slug = this.criarSlug(nome);
      const slugExistente = await this.prisma.parceiro.findUnique({
        where: { slug },
        select: { id: true },
      });
      if (slugExistente && slugExistente.id !== id) {
        throw new ConflictException(
          `Já existe um parceiro com o nome "${nome}".`,
        );
      }
    }

    const dominio =
      dados.dominio === undefined
        ? undefined
        : dados.dominio?.trim().toLowerCase() || null;
    if (dominio) {
      const dominioExistente = await this.prisma.parceiro.findUnique({
        where: { dominio },
        select: { id: true },
      });
      if (dominioExistente && dominioExistente.id !== id) {
        throw new ConflictException(
          `Já existe um parceiro com o domínio "${dominio}".`,
        );
      }
    }

    return this.prisma.parceiro.update({
      where: { id },
      data: {
        ...(nome !== undefined && { nome, slug }),
        ...(dados.logoUrl !== undefined && {
          logoUrl: dados.logoUrl?.trim() || null,
        }),
        ...(dados.site !== undefined && {
          site: dados.site?.trim() || null,
        }),
        ...(dados.dominio !== undefined && { dominio }),
        ...(dados.programaAfiliados !== undefined && {
          programaAfiliados: dados.programaAfiliados,
        }),
        ...(dados.observacao !== undefined && {
          observacao: dados.observacao?.trim() || null,
        }),
        ...(dados.ativo !== undefined && { ativo: dados.ativo }),
      },
    });
  }

  async removerParceiro(id: number) {
    const parceiro = await this.prisma.parceiro.findUnique({
      where: { id },
      select: {
        id: true,
        nome: true,
        _count: { select: { ofertas: true, sugestoesOfertas: true } },
      },
    });
    if (!parceiro) throw new NotFoundException('Parceiro não encontrado.');
    if (parceiro._count.ofertas > 0 || parceiro._count.sugestoesOfertas > 0) {
      throw new ConflictException(
        'Não é possível excluir este parceiro porque existem ofertas ou sugestões vinculadas. Desative-o ou remova os vínculos primeiro.',
      );
    }
    await this.prisma.parceiro.delete({ where: { id } });
    return { removido: true, id: parceiro.id, nome: parceiro.nome };
  }

  async listarOfertas() {
    const ofertas = await this.prisma.oferta.findMany({
      orderBy: { atualizadoEm: 'desc' },
      include: {
        produto: {
          select: { id: true, nome: true, slug: true, tipo: true },
        },
        hardware: { select: { id: true, nome: true, categoria: true } },
        parceiro: { select: { id: true, nome: true, slug: true } },
        usuarioOrigem: { select: { id: true, nome: true } },
      },
    });
    return { total: ofertas.length, ofertas };
  }

  async buscarOferta(id: number) {
    const oferta = await this.prisma.oferta.findUnique({
      where: { id },
      include: {
        produto: true,
        hardware: { select: { id: true, nome: true, categoria: true } },
        parceiro: true,
        usuarioOrigem: { select: { id: true, nome: true } },
      },
    });
    if (!oferta) throw new NotFoundException('Oferta não encontrada.');
    return oferta;
  }

  async criarOferta(dados: CriarOfertaDto) {
    if (
      (dados.produtoId === undefined && dados.hardwareId === undefined) ||
      (dados.produtoId !== undefined && dados.hardwareId !== undefined)
    ) {
      throw new BadRequestException(
        'Informe produtoId ou hardwareId, mas não os dois ao mesmo tempo.',
      );
    }

    let produtoId = dados.produtoId;
    let hardwareId: number | null = null;
    let nomeProduto = 'Produto';

    if (dados.hardwareId !== undefined) {
      const hardware = await this.prisma.hardware.findFirst({
        where: { id: dados.hardwareId, ativo: true },
        select: { id: true, nome: true, produtoId: true },
      });
      if (!hardware || !hardware.produtoId) {
        throw new NotFoundException(
          'Hardware não encontrado, inativo ou ainda não vinculado ao catálogo.',
        );
      }
      produtoId = hardware.produtoId;
      hardwareId = hardware.id;
      nomeProduto = hardware.nome;
    } else if (produtoId !== undefined) {
      const produto = await this.prisma.produto.findFirst({
        where: { id: produtoId, ativo: true },
        include: { hardware: { select: { id: true } } },
      });
      if (!produto) {
        throw new NotFoundException('Produto não encontrado ou inativo.');
      }
      hardwareId = produto.hardware?.id ?? null;
      nomeProduto = produto.nome;
    }

    if (produtoId === undefined) {
      throw new BadRequestException('Não foi possível identificar o produto.');
    }

    const parceiro = await this.prisma.parceiro.findFirst({
      where: { id: dados.parceiroId, ativo: true },
      select: { id: true, nome: true },
    });
    if (!parceiro) {
      throw new NotFoundException('Parceiro não encontrado ou inativo.');
    }

    const existente = await this.prisma.oferta.findFirst({
      where: {
        produtoId,
        parceiroId: dados.parceiroId,
        urlOriginal: dados.urlOriginal,
      },
      select: { id: true },
    });
    if (existente) {
      throw new ConflictException(
        `Esta oferta de "${nomeProduto}" já está cadastrada no parceiro "${parceiro.nome}".`,
      );
    }

    return this.prisma.oferta.create({
      data: {
        produtoId,
        hardwareId,
        parceiroId: dados.parceiroId,
        vendedorNome: dados.vendedorNome?.trim() ?? null,
        vendedorIdentificador: dados.vendedorIdentificador?.trim() ?? null,
        urlOriginal: dados.urlOriginal,
        urlAfiliada: dados.urlAfiliada ?? null,
        preco: dados.preco,
        precoAnterior: dados.precoAnterior ?? null,
        frete: dados.frete ?? null,
        validoAte: dados.validoAte ? new Date(dados.validoAte) : null,
        verificadoEm: new Date(),
        status: StatusOferta.ATIVA,
        coletadoEm: new Date(),
        historicoPrecos: {
          create: {
            preco: dados.preco,
            frete: dados.frete ?? null,
            verificadoEm: new Date(),
          },
        },
      },
      include: {
        produto: { select: { id: true, nome: true, slug: true } },
        hardware: { select: { id: true, nome: true, categoria: true } },
        parceiro: { select: { id: true, nome: true, slug: true } },
      },
    });
  }

  private async listarAtivasProduto(produtoId: number) {
    const agora = new Date();
    return this.prisma.oferta.findMany({
      where: {
        produtoId,
        status: StatusOferta.ATIVA,
        parceiro: { ativo: true },
        OR: [{ validoAte: null }, { validoAte: { gte: agora } }],
      },
      orderBy: { preco: 'asc' },
      select: {
        id: true,
        vendedorNome: true,
        vendedorIdentificador: true,
        preco: true,
        precoAnterior: true,
        frete: true,
        urlOriginal: true,
        urlAfiliada: true,
        validoAte: true,
        verificadoEm: true,
        status: true,
        atualizadoEm: true,
        usuarioOrigem: { select: { id: true, nome: true } },
        parceiro: {
          select: {
            id: true,
            nome: true,
            slug: true,
            logoUrl: true,
            programaAfiliados: true,
          },
        },
      },
    });
  }

  async listarOfertasDoProduto(produtoId: number) {
    const produto = await this.prisma.produto.findFirst({
      where: { id: produtoId, ativo: true, publicado: true },
      select: {
        id: true,
        nome: true,
        slug: true,
        usuarioOrigem: { select: { id: true, nome: true } },
      },
    });
    if (!produto) throw new NotFoundException('Produto não encontrado.');

    const ofertasBanco = await this.listarAtivasProduto(produtoId);
    const ofertas = ofertasBanco.map((oferta) => {
      const { usuarioOrigem, ...ofertaPublica } = oferta;
      return {
        ...ofertaPublica,
        cadastradoPor: usuarioOrigem,
        preco: Number(oferta.preco),
        precoAtual: Number(oferta.preco),
        precoAnterior:
          oferta.precoAnterior === null ? null : Number(oferta.precoAnterior),
        frete: oferta.frete === null ? null : Number(oferta.frete),
        percentualDesconto: this.calcularPercentualDesconto(
          oferta.preco,
          oferta.precoAnterior,
        ),
        urlAfiliado: oferta.urlAfiliada,
        urlCompra: oferta.urlAfiliada ?? oferta.urlOriginal,
        possuiLinkAfiliado: oferta.urlAfiliada !== null,
      };
    });
    const melhorOferta = ofertas[0] ?? null;

    const { usuarioOrigem, ...produtoPublico } = produto;

    return {
      produto: { ...produtoPublico, cadastradoPor: usuarioOrigem },
      total: ofertas.length,
      quantidadeOfertasAtivas: ofertas.length,
      melhorPreco: melhorOferta
        ? { preco: melhorOferta.preco, parceiro: melhorOferta.parceiro }
        : null,
      melhorOferta,
      ofertas,
    };
  }

  async listarDestaques() {
    const agora = new Date();
    const produtos = await this.prisma.produto.findMany({
      where: {
        ativo: true,
        publicado: true,
        ofertas: {
          some: {
            status: StatusOferta.ATIVA,
            parceiro: { ativo: true },
            OR: [{ validoAte: null }, { validoAte: { gte: agora } }],
          },
        },
      },
      orderBy: [{ atualizadoEm: 'desc' }, { id: 'desc' }],
      select: {
        id: true,
        nome: true,
        marca: true,
        imagemUrl: true,
        tipo: true,
        usuarioOrigem: { select: { id: true, nome: true } },
        categoria: {
          select: { id: true, nome: true, slug: true, grupo: true },
        },
        ofertas: {
          where: {
            status: StatusOferta.ATIVA,
            parceiro: { ativo: true },
            OR: [{ validoAte: null }, { validoAte: { gte: agora } }],
          },
          orderBy: [{ preco: 'asc' }, { id: 'asc' }],
          select: {
            id: true,
            vendedorNome: true,
            vendedorIdentificador: true,
            preco: true,
            precoAnterior: true,
            frete: true,
            urlOriginal: true,
            urlAfiliada: true,
            validoAte: true,
            verificadoEm: true,
            atualizadoEm: true,
            usuarioOrigem: { select: { id: true, nome: true } },
            parceiro: {
              select: {
                id: true,
                nome: true,
                slug: true,
                logoUrl: true,
                programaAfiliados: true,
              },
            },
          },
        },
      },
    });

    const destaques: {
      perifericos: Array<Record<string, unknown>>;
      hardwares: Array<Record<string, unknown>>;
      monitores: Array<Record<string, unknown>>;
      notebooks: Array<Record<string, unknown>>;
      setup: Array<Record<string, unknown>>;
    } = {
      perifericos: [],
      hardwares: [],
      monitores: [],
      notebooks: [],
      setup: [],
    };

    for (const produto of produtos) {
      const grupo = this.grupoDestaqueProduto(produto);
      const oferta = produto.ofertas[0];
      if (!grupo || !oferta) continue;

      const precoAtual = Number(oferta.preco);
      const precoAnterior =
        oferta.precoAnterior === null ? null : Number(oferta.precoAnterior);
      const percentualDesconto = this.calcularPercentualDesconto(
        oferta.preco,
        oferta.precoAnterior,
      );

      const item = {
        produtoId: produto.id,
        nome: produto.nome,
        marca: produto.marca,
        imagem: produto.imagemUrl,
        categoria: produto.categoria,
        cadastradoPor: produto.usuarioOrigem,
        grupo,
        melhorPreco: precoAtual,
        precoAnterior,
        percentualDesconto,
        quantidadeOfertas: produto.ofertas.length,
        melhorOferta: {
          id: oferta.id,
          vendedorNome: oferta.vendedorNome,
          vendedorIdentificador: oferta.vendedorIdentificador,
          preco: precoAtual,
          precoAtual,
          precoAnterior,
          percentualDesconto,
          frete: oferta.frete === null ? null : Number(oferta.frete),
          urlOriginal: oferta.urlOriginal,
          urlAfiliada: oferta.urlAfiliada,
          urlAfiliado: oferta.urlAfiliada,
          urlCompra: oferta.urlAfiliada ?? oferta.urlOriginal,
          possuiLinkAfiliado: oferta.urlAfiliada !== null,
          validoAte: oferta.validoAte,
          verificadoEm: oferta.verificadoEm,
          atualizadoEm: oferta.atualizadoEm,
          cadastradoPor: oferta.usuarioOrigem,
          parceiro: oferta.parceiro,
        },
      };

      if (grupo === 'HARDWARE') destaques.hardwares.push(item);
      else if (grupo === 'PERIFERICOS') destaques.perifericos.push(item);
      else if (grupo === 'MONITORES') destaques.monitores.push(item);
      else if (grupo === 'NOTEBOOKS') destaques.notebooks.push(item);
      else destaques.setup.push(item);
    }

    return destaques;
  }

  async listarOfertasDoHardware(hardwareId: number) {
    const hardware = await this.prisma.hardware.findFirst({
      where: { id: hardwareId, ativo: true, publicado: true },
      select: { id: true, nome: true, produtoId: true },
    });
    if (!hardware?.produtoId)
      throw new NotFoundException('Hardware não encontrado.');
    const resultado = await this.listarOfertasDoProduto(hardware.produtoId);
    return { hardware, ...resultado, produto: resultado.produto };
  }

  async statusVerificacaoPrecos() {
    const agora = new Date();
    const ha24Horas = new Date(agora.getTime() - 24 * 60 * 60 * 1000);
    const base = {
      status: { in: [StatusOferta.ATIVA, StatusOferta.INDISPONIVEL] },
      parceiro: { ativo: true },
      produto: { ativo: true },
      AND: [
        { OR: [{ urlOriginal: { not: '' } }, { urlAfiliada: { not: null } }] },
        { OR: [{ validoAte: null }, { validoAte: { gte: agora } }] },
      ],
    };

    const [elegiveis, nuncaVerificadas, desatualizadas, ultima] =
      await Promise.all([
        this.prisma.oferta.count({ where: base }),
        this.prisma.oferta.count({
          where: { ...base, verificadoEm: null },
        }),
        this.prisma.oferta.count({
          where: {
            ...base,
            verificadoEm: { lt: ha24Horas },
          },
        }),
        this.prisma.oferta.findFirst({
          where: { ...base, verificadoEm: { not: null } },
          orderBy: { verificadoEm: 'desc' },
          select: { verificadoEm: true },
        }),
      ]);

    return {
      elegiveis,
      nuncaVerificadas,
      desatualizadasMaisDe24h: desatualizadas,
      ultimaVerificacaoEm: ultima?.verificadoEm ?? null,
      observacao:
        'A verificação prioriza preço estruturado confiável. Se a consulta direta falhar, usa a Produto IA/Surfsky como fallback. Mudanças acima de 35% não são aplicadas automaticamente e ficam para revisão.',
    };
  }

  async verificarPrecosOfertas(limiteInformado?: number) {
    const limite = Math.min(Math.max(limiteInformado ?? 20, 1), 50);
    const agora = new Date();

    const ofertas = await this.prisma.oferta.findMany({
      where: {
        status: { in: [StatusOferta.ATIVA, StatusOferta.INDISPONIVEL] },
        parceiro: { ativo: true },
        produto: { ativo: true },
        AND: [
          {
            OR: [{ urlOriginal: { not: '' } }, { urlAfiliada: { not: null } }],
          },
          { OR: [{ validoAte: null }, { validoAte: { gte: agora } }] },
        ],
      },
      orderBy: [{ coletadoEm: 'asc' }, { id: 'asc' }],
      take: limite,
      select: {
        id: true,
        preco: true,
        urlOriginal: true,
        urlAfiliada: true,
        produto: { select: { id: true, nome: true } },
        parceiro: { select: { id: true, nome: true } },
      },
    });

    const totalElegiveisAntes = await this.prisma.oferta.count({
      where: {
        status: { in: [StatusOferta.ATIVA, StatusOferta.INDISPONIVEL] },
        parceiro: { ativo: true },
        produto: { ativo: true },
        AND: [
          {
            OR: [{ urlOriginal: { not: '' } }, { urlAfiliada: { not: null } }],
          },
          { OR: [{ validoAte: null }, { validoAte: { gte: agora } }] },
        ],
      },
    });

    const resultados: Array<{
      ofertaId: number;
      produtoId: number;
      produto: string;
      parceiro: string;
      status:
        | 'ATUALIZADA'
        | 'SEM_ALTERACAO'
        | 'REVISAR'
        | 'INDISPONIVEL'
        | 'FALHOU';
      precoAnterior: number;
      precoAtual: number | null;
      variacaoPercentual?: number;
      revisaoNecessaria?: boolean;
      urlConsultada?: 'ORIGINAL' | 'AFILIADA';
      urlFinal?: string;
      origemPreco?: 'JSON_LD' | 'META' | 'PRODUTO_IA';
      fontePreco?: string | null;
      viaProdutoIa?: boolean;
      motivo?: string;
    }> = [];

    for (const oferta of ofertas) {
      const precoSalvo = Number(oferta.preco);
      const verificacao = await this.verificadorPrecos.verificarOferta({
        urlOriginal: oferta.urlOriginal,
        urlAfiliada: oferta.urlAfiliada,
        precoAtual: precoSalvo,
      });

      if (verificacao.status === 'SUCESSO') {
        const mudouPreco = verificacao.preco !== precoSalvo;
        const verificadoEm = new Date();
        const { revisar, variacaoPercentual } =
          this.variacaoPrecoExigeRevisao(precoSalvo, verificacao.preco);

        if (mudouPreco && revisar) {
          // Proteção de preço: uma variação muito grande pode ser parcela,
          // variante, preço antigo ou outro item. Registra a tentativa, mas
          // NÃO altera preço/preçoAnterior/histórico automaticamente.
          await this.prisma.oferta.update({
            where: { id: oferta.id },
            data: {
              verificadoEm,
              coletadoEm: verificadoEm,
            },
          });

          resultados.push({
            ofertaId: oferta.id,
            produtoId: oferta.produto.id,
            produto: oferta.produto.nome,
            parceiro: oferta.parceiro.nome,
            status: 'REVISAR',
            precoAnterior: precoSalvo,
            precoAtual: verificacao.preco,
            variacaoPercentual,
            revisaoNecessaria: true,
            urlConsultada: verificacao.urlConsultada,
            urlFinal: verificacao.urlFinal,
            origemPreco: verificacao.origemPreco,
            fontePreco: verificacao.fontePreco ?? null,
            viaProdutoIa: verificacao.viaProdutoIa ?? false,
            motivo: `Variação de ${variacaoPercentual}% acima do limite automático de 35%. O preço salvo não foi alterado.`,
          });
          continue;
        }

        await this.prisma.$transaction(async (tx) => {
          await tx.oferta.update({
            where: { id: oferta.id },
            data: {
              ...(mudouPreco && {
                precoAnterior: oferta.preco,
                preco: verificacao.preco,
              }),
              verificadoEm,
              coletadoEm: verificadoEm,
              status: StatusOferta.ATIVA,
            },
          });

          if (mudouPreco) {
            await tx.historicoPrecoOferta.create({
              data: {
                ofertaId: oferta.id,
                preco: verificacao.preco,
                verificadoEm,
              },
            });
          }
        });

        resultados.push({
          ofertaId: oferta.id,
          produtoId: oferta.produto.id,
          produto: oferta.produto.nome,
          parceiro: oferta.parceiro.nome,
          status: mudouPreco ? 'ATUALIZADA' : 'SEM_ALTERACAO',
          precoAnterior: precoSalvo,
          precoAtual: verificacao.preco,
          variacaoPercentual,
          revisaoNecessaria: false,
          urlConsultada: verificacao.urlConsultada,
          urlFinal: verificacao.urlFinal,
          origemPreco: verificacao.origemPreco,
          fontePreco: verificacao.fontePreco ?? null,
          viaProdutoIa: verificacao.viaProdutoIa ?? false,
        });
        continue;
      }

      if (verificacao.status === 'INDISPONIVEL') {
        await this.prisma.oferta.update({
          where: { id: oferta.id },
          data: {
            status: StatusOferta.INDISPONIVEL,
            verificadoEm: new Date(),
          },
        });

        resultados.push({
          ofertaId: oferta.id,
          produtoId: oferta.produto.id,
          produto: oferta.produto.nome,
          parceiro: oferta.parceiro.nome,
          status: 'INDISPONIVEL',
          precoAnterior: precoSalvo,
          precoAtual: null,
          urlConsultada: verificacao.urlConsultada,
          urlFinal: verificacao.urlFinal,
          viaProdutoIa: verificacao.viaProdutoIa ?? false,
          motivo: verificacao.motivo,
        });
        continue;
      }

      await this.prisma.oferta.update({
        where: { id: oferta.id },
        data: { coletadoEm: new Date() },
      });

      resultados.push({
        ofertaId: oferta.id,
        produtoId: oferta.produto.id,
        produto: oferta.produto.nome,
        parceiro: oferta.parceiro.nome,
        status: 'FALHOU',
        precoAnterior: precoSalvo,
        precoAtual: null,
        urlConsultada: verificacao.urlConsultada,
        viaProdutoIa: verificacao.viaProdutoIa ?? false,
        motivo: verificacao.motivo,
      });
    }

    const resumo = {
      verificadas: resultados.length,
      atualizadas: resultados.filter((item) => item.status === 'ATUALIZADA')
        .length,
      semAlteracao: resultados.filter((item) => item.status === 'SEM_ALTERACAO')
        .length,
      revisar: resultados.filter((item) => item.status === 'REVISAR').length,
      indisponiveis: resultados.filter((item) => item.status === 'INDISPONIVEL')
        .length,
      falharam: resultados.filter((item) => item.status === 'FALHOU').length,
    };

    const restantesElegiveis = Math.max(
      0,
      totalElegiveisAntes - ofertas.length,
    );

    return {
      ...resumo,
      limiteDoLote: limite,
      restantesElegiveis,
      resultados,
      observacao:
        'Falha de verificação nunca altera o preço salvo. Variações acima de 35% ficam para revisão e não são aplicadas automaticamente. Quando a consulta direta falha, o backend tenta a Produto IA/Surfsky. Itens só são marcados como indisponíveis quando a fonte confirma indisponibilidade de forma objetiva.',
    };
  }

  async atualizarOferta(id: number, dados: AtualizarOfertaDto) {
    const oferta = await this.prisma.oferta.findUnique({
      where: { id },
      select: { id: true, preco: true, frete: true },
    });
    if (!oferta) throw new NotFoundException('Oferta não encontrada.');

    const precoNovo = dados.preco ?? oferta.preco;
    const freteNovo = dados.frete !== undefined ? dados.frete : oferta.frete;
    const mudouPreco =
      dados.preco !== undefined && Number(dados.preco) !== Number(oferta.preco);
    const freteAtual = oferta.frete === null ? null : Number(oferta.frete);
    const mudouFrete = dados.frete !== undefined && dados.frete !== freteAtual;
    const mudouPrecoOuFrete = mudouPreco || mudouFrete;

    return this.prisma.$transaction(async (tx) => {
      const atualizada = await tx.oferta.update({
        where: { id },
        data: {
          ...(dados.vendedorNome !== undefined && {
            vendedorNome:
              dados.vendedorNome === null
                ? null
                : dados.vendedorNome.trim() || null,
          }),
          ...(dados.vendedorIdentificador !== undefined && {
            vendedorIdentificador:
              dados.vendedorIdentificador === null
                ? null
                : dados.vendedorIdentificador.trim() || null,
          }),
          ...(dados.urlOriginal !== undefined && {
            urlOriginal: dados.urlOriginal,
          }),
          ...(dados.urlAfiliada !== undefined && {
            urlAfiliada: dados.urlAfiliada,
          }),
          ...(dados.preco !== undefined && {
            preco: dados.preco,
            precoAnterior:
              dados.precoAnterior !== undefined
                ? dados.precoAnterior
                : oferta.preco,
          }),
          ...(dados.preco === undefined &&
            dados.precoAnterior !== undefined && {
              precoAnterior: dados.precoAnterior,
            }),
          ...(dados.frete !== undefined && { frete: dados.frete }),
          ...(dados.validoAte !== undefined && {
            validoAte:
              dados.validoAte === null ? null : new Date(dados.validoAte),
          }),
          ...(dados.status !== undefined && { status: dados.status }),
          coletadoEm: new Date(),
          verificadoEm: new Date(),
        },
        include: {
          produto: { select: { id: true, nome: true, slug: true } },
          hardware: {
            select: { id: true, nome: true, categoria: true },
          },
          parceiro: { select: { id: true, nome: true, slug: true } },
        },
      });

      if (mudouPrecoOuFrete) {
        await tx.historicoPrecoOferta.create({
          data: {
            ofertaId: id,
            preco: precoNovo,
            frete: freteNovo,
            verificadoEm: new Date(),
          },
        });
      }

      return atualizada;
    });
  }

  async historicoOferta(id: number, exigirProdutoPublico = true) {
    const oferta = await this.prisma.oferta.findUnique({
      where: { id },
      select: {
        id: true,
        produtoId: true,
        status: true,
        validoAte: true,
        parceiro: { select: { ativo: true } },
        produto: {
          select: { id: true, nome: true, ativo: true, publicado: true },
        },
      },
    });

    if (!oferta) throw new NotFoundException('Oferta não encontrada.');
    if (exigirProdutoPublico) {
      const agora = new Date();
      const ofertaValida =
        oferta.status === StatusOferta.ATIVA &&
        oferta.parceiro.ativo &&
        (oferta.validoAte === null || oferta.validoAte >= agora);

      if (!oferta.produto.ativo || !oferta.produto.publicado || !ofertaValida) {
        throw new NotFoundException('Oferta não encontrada.');
      }
    }

    const historico = await this.prisma.historicoPrecoOferta.findMany({
      where: { ofertaId: id },
      orderBy: { verificadoEm: 'asc' },
      select: {
        id: true,
        preco: true,
        frete: true,
        verificadoEm: true,
      },
    });

    return {
      ofertaId: id,
      produto: { id: oferta.produto.id, nome: oferta.produto.nome },
      total: historico.length,
      historico,
    };
  }

  async removerOferta(id: number) {
    const oferta = await this.prisma.oferta.findUnique({
      where: { id },
      select: { id: true, status: true },
    });
    if (!oferta) throw new NotFoundException('Oferta não encontrada.');

    if (oferta.status !== StatusOferta.DESCONTINUADA) {
      await this.prisma.oferta.update({
        where: { id },
        data: {
          status: StatusOferta.DESCONTINUADA,
          verificadoEm: new Date(),
        },
      });
    }

    return {
      mensagem: 'Oferta descontinuada com sucesso.',
      ofertaId: id,
      status: StatusOferta.DESCONTINUADA,
    };
  }

  async calcularPrecoTotal(hardwareIds: number[]) {
    if (hardwareIds.length === 0) return { total: 0, itens: [] };
    const ofertas = await this.prisma.oferta.findMany({
      where: {
        hardwareId: { in: hardwareIds },
        status: StatusOferta.ATIVA,
        parceiro: { ativo: true },
        OR: [{ validoAte: null }, { validoAte: { gte: new Date() } }],
      },
      orderBy: { preco: 'asc' },
      select: {
        hardwareId: true,
        preco: true,
        urlAfiliada: true,
        urlOriginal: true,
        parceiro: {
          select: { id: true, nome: true, slug: true, logoUrl: true },
        },
        hardware: { select: { id: true, nome: true, categoria: true } },
      },
    });

    const melhorPorHardware = new Map<number, (typeof ofertas)[0]>();
    for (const oferta of ofertas) {
      if (
        oferta.hardwareId !== null &&
        !melhorPorHardware.has(oferta.hardwareId)
      ) {
        melhorPorHardware.set(oferta.hardwareId, oferta);
      }
    }

    const itens = hardwareIds.map((hardwareId) => {
      const melhor = melhorPorHardware.get(hardwareId);
      return {
        hardwareId,
        hardware: melhor?.hardware ?? null,
        melhorOferta: melhor
          ? {
              preco: Number(melhor.preco),
              parceiro: melhor.parceiro,
              url: melhor.urlAfiliada ?? melhor.urlOriginal,
            }
          : null,
      };
    });
    const total = itens.reduce(
      (soma, item) => soma + (item.melhorOferta?.preco ?? 0),
      0,
    );
    const semOferta = itens.filter((item) => item.melhorOferta === null).length;
    return {
      total: Number(total.toFixed(2)),
      semOferta,
      aviso:
        semOferta > 0
          ? `${semOferta} componente(s) sem oferta cadastrada. Preço total pode estar incompleto.`
          : null,
      itens,
    };
  }
}
