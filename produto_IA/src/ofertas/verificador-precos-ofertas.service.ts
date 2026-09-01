import { Injectable } from '@nestjs/common';
import {
  obterCabecalhoHttp,
  requisitarUrlPublicaUmaVez,
  validarUrlPublica,
} from '../common/security/external-http-security';

export type OrigemPrecoVerificado = 'JSON_LD' | 'META' | 'PRODUTO_IA';

type ResultadoConsultaPreco =
  | {
      status: 'SUCESSO';
      preco: number;
      urlFinal: string;
      origemPreco: OrigemPrecoVerificado;
      fontePreco?: string | null;
    }
  | {
      status: 'INDISPONIVEL';
      urlFinal: string;
      motivo: string;
    }
  | {
      status: 'FALHOU';
      motivo: string;
    };

export type ResultadoVerificacaoOferta = ResultadoConsultaPreco & {
  urlConsultada?: 'ORIGINAL' | 'AFILIADA';
  viaProdutoIa?: boolean;
};

type PrecoExtraido = {
  preco: number | null;
  origem: OrigemPrecoVerificado | null;
  indisponivel: boolean;
};

type CandidatoPrecoJson = {
  preco: number;
  pontos: number;
  caminho: string;
};

@Injectable()
export class VerificadorPrecosOfertasService {
  // Marketplaces atuais costumam entregar HTML/estado de hidratação acima de 2 MB.
  // O limite continua finito para evitar consumo ilimitado de memória.
  private readonly limiteHtmlBytes = 5_000_000;
  private readonly maximoRedirecionamentos = 4;
  private readonly timeoutProdutoIaMs = 90_000;

  private extrairCodigoMarketplace(url: string): string | null {
    const texto = url.trim();
    if (!texto) return null;

    const magalu = /\/p\/([a-z0-9]+)(?:\/|\?|$)/iu.exec(texto)?.[1];
    if (magalu) return magalu.toLowerCase();

    const ml = /\b(ML[A-Z]{1,2}-?\d{5,})\b/iu.exec(texto)?.[1];
    if (ml) return ml.replace(/-/g, '').toLowerCase();

    const shopee = /(?:-i\.|product\/)(\d+)\.(\d+)/iu.exec(texto);
    if (shopee) return `${shopee[1]}.${shopee[2]}`;

    return null;
  }

  private normalizarCodigoMarketplace(valor: unknown): string | null {
    if (typeof valor !== 'string') return null;
    const limpo = valor.trim().replace(/-/g, '').toLowerCase();
    return limpo || null;
  }

  private async consultarProdutoIa(
    url: string,
  ): Promise<ResultadoConsultaPreco> {
    const base = process.env.PRODUTO_IA_URL?.trim().replace(/\/+$/, '');
    const apiKey = process.env.PRODUTO_IA_API_KEY?.trim();
    if (!base || !apiKey) {
      return {
        status: 'FALHOU',
        motivo: 'Produto IA não configurada para o fallback de preço.',
      };
    }

    const controller = new AbortController();
    const timeout = setTimeout(
      () => controller.abort(),
      this.timeoutProdutoIaMs,
    );

    try {
      const resposta = await fetch(`${base}/analisar`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': apiKey,
        },
        body: JSON.stringify({
          url,
          categoria: null,
          enrich: false,
          criabytePlan: false,
          noBrowser: false,
        }),
        signal: controller.signal,
      });

      if (!resposta.ok) {
        return {
          status: 'FALHOU',
          motivo: `Produto IA respondeu HTTP ${resposta.status}.`,
        };
      }

      const resultado = (await resposta.json()) as unknown;
      if (!this.ehRegistro(resultado)) {
        return {
          status: 'FALHOU',
          motivo: 'Produto IA retornou formato inválido.',
        };
      }

      const erro = typeof resultado.erro === 'string' ? resultado.erro : null;
      if (erro) {
        return { status: 'FALHOU', motivo: `Produto IA: ${erro}.` };
      }

      const oferta = this.ehRegistro(resultado.ofertaColetada)
        ? resultado.ofertaColetada
        : null;
      if (!oferta) {
        return {
          status: 'FALHOU',
          motivo: 'Produto IA não retornou oferta coletada.',
        };
      }

      const disponivel = oferta.disponivel;
      const urlFinal =
        (typeof oferta.urlProduto === 'string' && oferta.urlProduto.trim()) ||
        (typeof oferta.urlOriginal === 'string' && oferta.urlOriginal.trim()) ||
        url;

      if (disponivel === false) {
        return {
          status: 'INDISPONIVEL',
          urlFinal,
          motivo: 'Produto IA confirmou indisponibilidade da oferta.',
        };
      }

      const preco = this.normalizarPreco(oferta.preco);
      if (preco === null) {
        return {
          status: 'FALHOU',
          motivo: 'Produto IA não retornou preço confiável.',
        };
      }

      const codigoEsperado = this.extrairCodigoMarketplace(url);
      const codigoColetado = this.normalizarCodigoMarketplace(
        oferta.codigoMarketplace,
      );
      if (
        codigoEsperado &&
        codigoColetado &&
        codigoEsperado !== codigoColetado
      ) {
        return {
          status: 'FALHOU',
          motivo: `Produto IA retornou outro item (${codigoColetado}). O preço não foi alterado.`,
        };
      }

      const codigoFinal = this.extrairCodigoMarketplace(urlFinal);
      if (codigoEsperado && codigoFinal && codigoEsperado !== codigoFinal) {
        return {
          status: 'FALHOU',
          motivo: 'A URL final aponta para outro item. O preço não foi alterado.',
        };
      }

      return {
        status: 'SUCESSO',
        preco,
        urlFinal,
        origemPreco: 'PRODUTO_IA',
        fontePreco:
          typeof oferta.fontePreco === 'string' ? oferta.fontePreco : null,
      };
    } catch (erro) {
      const motivo =
        erro instanceof Error && erro.name === 'AbortError'
          ? 'Timeout ao consultar a Produto IA.'
          : erro instanceof Error
            ? erro.message
            : 'Falha ao consultar a Produto IA.';
      return { status: 'FALHOU', motivo };
    } finally {
      clearTimeout(timeout);
    }
  }

  private ehRegistro(valor: unknown): valor is Record<string, unknown> {
    return typeof valor === 'object' && valor !== null && !Array.isArray(valor);
  }

  private normalizarPreco(valor: unknown): number | null {
    if (typeof valor === 'number') {
      return Number.isFinite(valor) && valor > 0
        ? Number(valor.toFixed(2))
        : null;
    }
    if (typeof valor !== 'string') return null;

    let texto = valor
      .replace(/\u00a0/g, ' ')
      .replace(/R\$/gi, '')
      .replace(/[^0-9.,]/g, '')
      .trim();
    if (!texto) return null;

    const ultimaVirgula = texto.lastIndexOf(',');
    const ultimoPonto = texto.lastIndexOf('.');

    if (ultimaVirgula >= 0 && ultimoPonto >= 0) {
      const decimal = ultimaVirgula > ultimoPonto ? ',' : '.';
      const milhar = decimal === ',' ? '.' : ',';
      texto = texto.split(milhar).join('');
      if (decimal === ',') texto = texto.replace(',', '.');
    } else if (ultimaVirgula >= 0) {
      const casas = texto.length - ultimaVirgula - 1;
      texto =
        casas >= 1 && casas <= 2
          ? texto.replace(',', '.')
          : texto.replace(/,/g, '');
    } else if (ultimoPonto >= 0) {
      const casas = texto.length - ultimoPonto - 1;
      if (!(casas >= 1 && casas <= 2)) texto = texto.replace(/\./g, '');
    }

    const numero = Number(texto);
    return Number.isFinite(numero) && numero > 0
      ? Number(numero.toFixed(2))
      : null;
  }

  private normalizarPrecoJson(valor: unknown, hostname: string): number | null {
    if (
      hostname.includes('shopee.') &&
      typeof valor === 'number' &&
      Number.isInteger(valor) &&
      valor >= 1_000_000
    ) {
      // A Shopee frequentemente serializa preço em unidades de 1/100000.
      const convertido = valor / 100_000;
      if (convertido > 0 && convertido < 10_000_000) {
        return Number(convertido.toFixed(2));
      }
    }

    if (
      hostname.includes('shopee.') &&
      typeof valor === 'string' &&
      /^\d{7,15}$/u.test(valor.trim())
    ) {
      const convertido = Number(valor) / 100_000;
      if (
        Number.isFinite(convertido) &&
        convertido > 0 &&
        convertido < 10_000_000
      ) {
        return Number(convertido.toFixed(2));
      }
    }

    return this.normalizarPreco(valor);
  }

  private tipoJsonLd(valor: unknown): string[] {
    if (typeof valor === 'string') return [valor.toLowerCase()];
    if (Array.isArray(valor)) {
      return valor
        .filter((item): item is string => typeof item === 'string')
        .map((item) => item.toLowerCase());
    }
    return [];
  }

  private buscarPrecoEmJsonLd(valor: unknown, profundidade = 0): number | null {
    if (profundidade > 10 || valor === null || valor === undefined) return null;
    if (Array.isArray(valor)) {
      for (const item of valor) {
        const encontrado = this.buscarPrecoEmJsonLd(item, profundidade + 1);
        if (encontrado !== null) return encontrado;
      }
      return null;
    }
    if (!this.ehRegistro(valor)) return null;

    const tipos = this.tipoJsonLd(valor['@type']);
    const ehOferta = tipos.some((tipo) => tipo.endsWith('offer'));
    const ehProduto = tipos.some((tipo) => tipo.endsWith('product'));

    if (ehOferta) {
      const preco = this.normalizarPreco(valor.price);
      if (preco !== null) return preco;
      const baixo = this.normalizarPreco(valor.lowPrice);
      if (baixo !== null) return baixo;
      if (this.ehRegistro(valor.priceSpecification)) {
        const especificado = this.normalizarPreco(
          valor.priceSpecification.price,
        );
        if (especificado !== null) return especificado;
      }
    }

    if (ehProduto && valor.offers !== undefined) {
      const precoOferta = this.buscarPrecoEmJsonLd(
        valor.offers,
        profundidade + 1,
      );
      if (precoOferta !== null) return precoOferta;
    }

    for (const [chave, filho] of Object.entries(valor)) {
      if (!['@graph', 'mainEntity', 'itemListElement'].includes(chave))
        continue;
      const encontrado = this.buscarPrecoEmJsonLd(filho, profundidade + 1);
      if (encontrado !== null) return encontrado;
    }

    return null;
  }

  private jsonLdIndicaIndisponivel(valor: unknown, profundidade = 0): boolean {
    if (profundidade > 10 || valor === null || valor === undefined)
      return false;
    if (Array.isArray(valor)) {
      return valor.some((item) =>
        this.jsonLdIndicaIndisponivel(item, profundidade + 1),
      );
    }
    if (!this.ehRegistro(valor)) return false;

    const disponibilidade =
      typeof valor.availability === 'string'
        ? valor.availability.toLowerCase()
        : '';
    if (
      disponibilidade.endsWith('/outofstock') ||
      disponibilidade.endsWith('/discontinued') ||
      disponibilidade === 'outofstock' ||
      disponibilidade === 'discontinued'
    ) {
      return true;
    }

    return Object.entries(valor).some(([chave, filho]) =>
      ['offers', '@graph', 'mainEntity', 'itemListElement'].includes(chave)
        ? this.jsonLdIndicaIndisponivel(filho, profundidade + 1)
        : false,
    );
  }

  private extrairJsonLd(html: string): unknown[] {
    const resultados: unknown[] = [];
    const regex =
      /<script\b[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
    for (const match of html.matchAll(regex)) {
      const bruto = match[1]?.trim();
      if (!bruto || bruto.length > 1_000_000) continue;
      try {
        resultados.push(JSON.parse(bruto) as unknown);
      } catch {
        // JSON-LD malformado é ignorado; não inferimos preço por texto solto.
      }
    }
    return resultados;
  }

  private extrairPrecoMeta(html: string): number | null {
    const padroes = [
      /<meta\b[^>]*(?:property|name)=["']product:price:amount["'][^>]*content=["']([^"']+)["'][^>]*>/i,
      /<meta\b[^>]*content=["']([^"']+)["'][^>]*(?:property|name)=["']product:price:amount["'][^>]*>/i,
      /<meta\b[^>]*(?:property|name)=["']og:price:amount["'][^>]*content=["']([^"']+)["'][^>]*>/i,
      /<meta\b[^>]*content=["']([^"']+)["'][^>]*(?:property|name)=["']og:price:amount["'][^>]*>/i,
      /<meta\b[^>]*itemprop=["']price["'][^>]*content=["']([^"']+)["'][^>]*>/i,
      /<meta\b[^>]*content=["']([^"']+)["'][^>]*itemprop=["']price["'][^>]*>/i,
      /<(?:span|div)\b[^>]*itemprop=["']price["'][^>]*content=["']([^"']+)["'][^>]*>/i,
      /<(?:span|div)\b[^>]*content=["']([^"']+)["'][^>]*itemprop=["']price["'][^>]*>/i,
      /<(?:div|span)\b[^>]*data-(?:product-)?price=["']([^"']+)["'][^>]*>/i,
    ];

    for (const padrao of padroes) {
      const preco = this.normalizarPreco(padrao.exec(html)?.[1]);
      if (preco !== null) return preco;
    }
    return null;
  }

  private extrairScriptsJson(html: string): unknown[] {
    const resultados: unknown[] = [];
    const regex = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;

    for (const match of html.matchAll(regex)) {
      const atributos = match[1] ?? '';
      const corpo = match[2]?.trim() ?? '';
      if (!corpo || corpo.length > 3_500_000) continue;

      const ehJson =
        /type=["']application\/(?:json|ld\+json)["']/i.test(atributos) ||
        /id=["'](?:__NEXT_DATA__|__NUXT_DATA__|__APOLLO_STATE__)["']/i.test(
          atributos,
        );
      if (!ehJson || (!corpo.startsWith('{') && !corpo.startsWith('['))) {
        continue;
      }

      try {
        resultados.push(JSON.parse(corpo) as unknown);
      } catch {
        // Estados de hidratação incompletos/malformados são ignorados.
      }
    }

    return resultados;
  }

  private chavePrecoPontuacao(chave: string, caminhoPai: string): number {
    const normalizada = chave.toLowerCase().replace(/[^a-z0-9]/g, '');
    const caminho = caminhoPai.toLowerCase().replace(/[^a-z0-9]/g, '');
    const composto = `${caminho}${normalizada}`;

    if (
      /(installment|parcel|freight|shipping|delivery|coupon|cupom|saving|discountpercent|percentage|tax|fee)/u.test(
        composto,
      )
    ) {
      return -100;
    }

    if (
      /(pricebefore|beforeprice|oldprice|originalprice|listprice|regularprice|previousprice|compareat|pricefrom)/u.test(
        composto,
      )
    ) {
      return -80;
    }

    if (/^(pixprice|pricepix|cashprice|bestprice)$/u.test(normalizada))
      return 150;
    if (
      /^(finalprice|currentprice|saleprice|sellingprice|promotionalprice|discountedprice|offerprice)$/u.test(
        normalizada,
      )
    ) {
      return 135;
    }
    if (/^(priceto|pricevalue|unitprice)$/u.test(normalizada)) return 115;
    if (/^(price|minprice|pricemin|price_min)$/u.test(normalizada)) return 95;

    if (
      /^(amount|value)$/u.test(normalizada) &&
      /(price|offer|sale|selling|pix|cash|current|final)/u.test(caminho)
    ) {
      return 105;
    }

    return -20;
  }

  private buscarCandidatosPrecoJson(
    valor: unknown,
    hostname: string,
    caminho: string[] = [],
    profundidade = 0,
    resultados: CandidatoPrecoJson[] = [],
  ): CandidatoPrecoJson[] {
    if (profundidade > 14 || resultados.length > 300) return resultados;

    if (Array.isArray(valor)) {
      for (let indice = 0; indice < Math.min(valor.length, 80); indice++) {
        this.buscarCandidatosPrecoJson(
          valor[indice],
          hostname,
          [...caminho, String(indice)],
          profundidade + 1,
          resultados,
        );
      }
      return resultados;
    }

    if (!this.ehRegistro(valor)) return resultados;

    for (const [chave, filho] of Object.entries(valor)) {
      const caminhoPai = caminho.join('.');
      const pontos = this.chavePrecoPontuacao(chave, caminhoPai);

      if (
        pontos > 0 &&
        (typeof filho === 'number' || typeof filho === 'string')
      ) {
        const preco = this.normalizarPrecoJson(filho, hostname);
        if (preco !== null && preco >= 0.5 && preco < 10_000_000) {
          resultados.push({
            preco,
            pontos,
            caminho: [...caminho, chave].join('.'),
          });
        }
      }

      if (typeof filho === 'object' && filho !== null) {
        this.buscarCandidatosPrecoJson(
          filho,
          hostname,
          [...caminho, chave],
          profundidade + 1,
          resultados,
        );
      }
    }

    return resultados;
  }

  private extrairPrecoJsonEmbutido(
    html: string,
    hostname: string,
  ): number | null {
    const estados = this.extrairScriptsJson(html);
    const candidatos: CandidatoPrecoJson[] = [];

    for (const estado of estados) {
      this.buscarCandidatosPrecoJson(estado, hostname, [], 0, candidatos);
    }

    const confiaveis = candidatos
      .filter((candidato) => candidato.pontos >= 95)
      .sort(
        (a, b) => b.pontos - a.pontos || a.caminho.length - b.caminho.length,
      );

    return confiaveis[0]?.preco ?? null;
  }

  private decodificarEntidadesBasicas(texto: string): string {
    return texto
      .replace(/&nbsp;|&#160;|&#x0*a0;/gi, ' ')
      .replace(/&quot;|&#34;|&#x0*22;/gi, '"')
      .replace(/&apos;|&#39;|&#x0*27;/gi, "'")
      .replace(/&amp;|&#38;|&#x0*26;/gi, '&')
      .replace(/&lt;|&#60;|&#x0*3c;/gi, '<')
      .replace(/&gt;|&#62;|&#x0*3e;/gi, '>');
  }

  private textoVisivel(html: string): string {
    return this.decodificarEntidadesBasicas(
      html
        .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ')
        .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ' ')
        .replace(/<noscript\b[^>]*>[\s\S]*?<\/noscript>/gi, ' ')
        .replace(/<[^>]+>/g, ' '),
    )
      .replace(/\s+/g, ' ')
      .trim();
  }

  private extrairPrecoAntesDoRotulo(
    texto: string,
    rotulo: RegExp,
    distanciaMaxima: number,
  ): number | null {
    const ocorrenciasRotulo = Array.from(texto.matchAll(rotulo));
    const precos = Array.from(
      texto.matchAll(
        /R\$\s*([0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{1,2})|[0-9]+(?:[.,][0-9]{1,2})?)/gi,
      ),
    );

    for (const alvo of ocorrenciasRotulo) {
      const posicaoRotulo = alvo.index ?? -1;
      if (posicaoRotulo < 0) continue;

      const anteriores = precos
        .filter((preco) => {
          const posicao = preco.index ?? -1;
          return (
            posicao >= 0 &&
            posicao < posicaoRotulo &&
            posicaoRotulo - posicao <= distanciaMaxima
          );
        })
        .sort((a, b) => (b.index ?? 0) - (a.index ?? 0));

      const valor = this.normalizarPreco(anteriores[0]?.[1]);
      if (valor !== null) return valor;
    }

    return null;
  }

  private extrairPrecoMercadoLivre(html: string): number | null {
    const regioes = Array.from(
      html.matchAll(
        /<(?:div|section)\b[^>]*class=["'][^"']*(?:ui-pdp-price__second-line|ui-pdp-price__main-container)[^"']*["'][^>]*>([\s\S]{0,12_000}?)(?:<\/(?:div|section)>)/gi,
      ),
    );

    const alvos =
      regioes.length > 0 ? regioes.map((item) => item[1] ?? '') : [html];
    for (const alvo of alvos) {
      const fracao =
        /class=["'][^"']*andes-money-amount__fraction[^"']*["'][^>]*>\s*([0-9.]+)\s*</i.exec(
          alvo,
        )?.[1];
      if (!fracao) continue;

      const centavos =
        /class=["'][^"']*andes-money-amount__cents[^"']*["'][^>]*>\s*([0-9]{1,2})\s*</i.exec(
          alvo,
        )?.[1];
      const preco = this.normalizarPreco(
        centavos ? `${fracao},${centavos.padEnd(2, '0')}` : fracao,
      );
      if (preco !== null) return preco;
    }

    return null;
  }

  private extrairPrecoMagalu(html: string): number | null {
    const texto = this.textoVisivel(html).slice(0, 120_000);

    const pix = this.extrairPrecoAntesDoRotulo(texto, /\bno\s+pix\b/gi, 120);
    if (pix !== null) return pix;

    const padroes = [
      /(?:preço|por)\s*R\$\s*([0-9.]+(?:,[0-9]{1,2})?)/i,
      /R\$\s*([0-9.]+(?:,[0-9]{1,2})?)\s*(?:à vista|a vista)/i,
    ];
    for (const padrao of padroes) {
      const preco = this.normalizarPreco(padrao.exec(texto)?.[1]);
      if (preco !== null) return preco;
    }

    return null;
  }

  private extrairPrecoShopee(html: string): number | null {
    const texto = this.textoVisivel(html).slice(0, 80_000);
    const ocorrencias = Array.from(
      texto.matchAll(/R\$\s*([0-9.]+(?:,[0-9]{1,2})?)/gi),
    );

    for (const ocorrencia of ocorrencias.slice(0, 12)) {
      const posicao = ocorrencia.index ?? 0;
      const contextoAntes = texto
        .slice(Math.max(0, posicao - 55), posicao)
        .toLowerCase();
      const contextoDepois = texto.slice(posicao, posicao + 35).toLowerCase();
      if (
        /frete|cupom|parcela|cashback/u.test(contextoAntes) ||
        /\bx\s+de\b|parcela/u.test(contextoDepois)
      ) {
        continue;
      }

      const preco = this.normalizarPreco(ocorrencia[1]);
      if (preco !== null) return preco;
    }

    return null;
  }

  private extrairPrecoMarketplace(
    html: string,
    hostname: string,
  ): number | null {
    const host = hostname.toLowerCase();

    if (host.includes('mercadolivre.') || host.includes('mercadolibre.')) {
      return this.extrairPrecoMercadoLivre(html);
    }
    if (host.includes('magazineluiza.')) {
      return this.extrairPrecoMagalu(html);
    }
    if (host.includes('shopee.')) {
      return this.extrairPrecoShopee(html);
    }

    return null;
  }

  private extrairPrecoEstruturado(html: string, url?: URL): PrecoExtraido {
    const jsonLd = this.extrairJsonLd(html);
    for (const item of jsonLd) {
      const preco = this.buscarPrecoEmJsonLd(item);
      if (preco !== null) {
        return { preco, origem: 'JSON_LD', indisponivel: false };
      }
    }

    const indisponivel = jsonLd.some((item) =>
      this.jsonLdIndicaIndisponivel(item),
    );
    if (indisponivel) {
      return { preco: null, origem: null, indisponivel: true };
    }

    const precoMeta = this.extrairPrecoMeta(html);
    if (precoMeta !== null) {
      return { preco: precoMeta, origem: 'META', indisponivel: false };
    }

    const hostname = url?.hostname.toLowerCase() ?? '';
    const precoJson = this.extrairPrecoJsonEmbutido(html, hostname);
    if (precoJson !== null) {
      return {
        preco: precoJson,
        origem: 'JSON_EMBUTIDO',
        indisponivel: false,
      };
    }

    const precoMarketplace = this.extrairPrecoMarketplace(html, hostname);
    if (precoMarketplace !== null) {
      return {
        preco: precoMarketplace,
        origem: 'HTML_MARKETPLACE',
        indisponivel: false,
      };
    }

    return { preco: null, origem: null, indisponivel: false };
  }

  private paginaPareceBloqueio(html: string): boolean {
    const inicio = this.textoVisivel(html).slice(0, 12_000).toLowerCase();
    return [
      'access denied',
      'captcha',
      'verifique que você é humano',
      'verifique que voce e humano',
      'robot or human',
      'unusual traffic',
    ].some((trecho) => inicio.includes(trecho));
  }

  private async consultarUrl(valor: string): Promise<ResultadoConsultaPreco> {
    let atual: URL;
    try {
      atual = (await validarUrlPublica(valor)).url;
    } catch (erro) {
      return {
        status: 'FALHOU',
        motivo: erro instanceof Error ? erro.message : 'URL inválida.',
      };
    }

    for (
      let redirecionamentos = 0;
      redirecionamentos <= this.maximoRedirecionamentos;
      redirecionamentos++
    ) {
      let resposta: Awaited<ReturnType<typeof requisitarUrlPublicaUmaVez>>;
      try {
        resposta = await requisitarUrlPublicaUmaVez(atual, {
          timeoutMs: 15_000,
          limiteRespostaBytes: this.limiteHtmlBytes,
          headers: {
            'User-Agent':
              'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
            Accept:
              'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.7',
            'Cache-Control': 'no-cache',
            Pragma: 'no-cache',
            'Upgrade-Insecure-Requests': '1',
          },
        });
      } catch (erro) {
        return {
          status: 'FALHOU',
          motivo:
            erro instanceof Error
              ? erro.message
              : 'Falha de rede ao consultar a página.',
        };
      }

      if (resposta.status >= 300 && resposta.status < 400) {
        const local = obterCabecalhoHttp(resposta, 'location');
        if (!local) {
          return {
            status: 'FALHOU',
            motivo: 'Redirecionamento sem destino.',
          };
        }
        if (redirecionamentos >= this.maximoRedirecionamentos) {
          return {
            status: 'FALHOU',
            motivo: 'Excesso de redirecionamentos.',
          };
        }
        try {
          atual = (await validarUrlPublica(new URL(local, atual))).url;
        } catch (erro) {
          return {
            status: 'FALHOU',
            motivo:
              erro instanceof Error
                ? erro.message
                : 'Destino de redirecionamento inválido.',
          };
        }
        continue;
      }

      if (resposta.status === 404 || resposta.status === 410) {
        return {
          status: 'INDISPONIVEL',
          urlFinal: atual.toString(),
          motivo: `A página retornou HTTP ${resposta.status}.`,
        };
      }

      if (!resposta.ok) {
        return {
          status: 'FALHOU',
          motivo: `A página retornou HTTP ${resposta.status}.`,
        };
      }

      const contentType = obterCabecalhoHttp(resposta, 'content-type') ?? '';
      if (!contentType.toLowerCase().includes('text/html')) {
        return {
          status: 'FALHOU',
          motivo: 'A URL não retornou HTML.',
        };
      }

      const html = resposta.corpo.toString('utf8');
      if (this.paginaPareceBloqueio(html)) {
        return {
          status: 'FALHOU',
          motivo:
            'O marketplace bloqueou a consulta automática desta página. O valor salvo não foi alterado.',
        };
      }

      const extraido = this.extrairPrecoEstruturado(html, atual);
      if (extraido.indisponivel) {
        return {
          status: 'INDISPONIVEL',
          urlFinal: atual.toString(),
          motivo: 'Os dados estruturados indicam item indisponível.',
        };
      }
      if (extraido.preco !== null && extraido.origem !== null) {
        return {
          status: 'SUCESSO',
          preco: extraido.preco,
          urlFinal: atual.toString(),
          origemPreco: extraido.origem === 'JSON_LD' ? 'JSON_LD' : 'META',
          fontePreco: null,
        };
      }

      return {
        status: 'FALHOU',
        motivo:
          'Não foi encontrado preço confiável na página. O valor salvo não foi alterado.',
      };
    }

    return { status: 'FALHOU', motivo: 'Não foi possível verificar a URL.' };
  }

  private precisaConfirmacaoProdutoIa(
    precoAtual: number | undefined,
    precoEncontrado: number,
  ): boolean {
    if (
      precoAtual === undefined ||
      !Number.isFinite(precoAtual) ||
      precoAtual <= 0
    ) {
      return false;
    }

    const variacao =
      (Math.abs(precoEncontrado - precoAtual) / precoAtual) * 100;
    return variacao > 35;
  }

  private async confirmarComProdutoIaSeSuspeito(
    resultado: Extract<ResultadoConsultaPreco, { status: 'SUCESSO' }>,
    url: string,
    precoAtual?: number,
  ): Promise<{ resultado: ResultadoConsultaPreco; viaProdutoIa: boolean }> {
    if (!this.precisaConfirmacaoProdutoIa(precoAtual, resultado.preco)) {
      return { resultado, viaProdutoIa: false };
    }

    const confirmado = await this.consultarProdutoIa(url);
    if (confirmado.status === 'SUCESSO') {
      return { resultado: confirmado, viaProdutoIa: true };
    }

    // Se a IA não conseguir confirmar, preserva o candidato direto. A camada
    // de Ofertas bloqueará a alteração automática por causa da variação >35%.
    return { resultado, viaProdutoIa: false };
  }

  async verificarOferta(dados: {
    urlOriginal: string;
    urlAfiliada: string | null;
    precoAtual?: number;
  }): Promise<ResultadoVerificacaoOferta> {
    const original = await this.consultarUrl(dados.urlOriginal);
    if (original.status === 'SUCESSO') {
      const confirmado = await this.confirmarComProdutoIaSeSuspeito(
        original,
        dados.urlOriginal,
        dados.precoAtual,
      );
      return {
        ...confirmado.resultado,
        urlConsultada: 'ORIGINAL',
        viaProdutoIa: confirmado.viaProdutoIa,
      } as ResultadoVerificacaoOferta;
    }

    if (dados.urlAfiliada && dados.urlAfiliada !== dados.urlOriginal) {
      const afiliada = await this.consultarUrl(dados.urlAfiliada);
      if (afiliada.status === 'SUCESSO') {
        const confirmado = await this.confirmarComProdutoIaSeSuspeito(
          afiliada,
          dados.urlAfiliada,
          dados.precoAtual,
        );
        return {
          ...confirmado.resultado,
          urlConsultada: 'AFILIADA',
          viaProdutoIa: confirmado.viaProdutoIa,
        } as ResultadoVerificacaoOferta;
      }
      if (
        original.status === 'INDISPONIVEL' &&
        afiliada.status === 'INDISPONIVEL'
      ) {
        return { ...original, urlConsultada: 'ORIGINAL', viaProdutoIa: false };
      }

      const iaOriginal = await this.consultarProdutoIa(dados.urlOriginal);
      if (
        iaOriginal.status === 'SUCESSO' ||
        iaOriginal.status === 'INDISPONIVEL'
      ) {
        return { ...iaOriginal, urlConsultada: 'ORIGINAL', viaProdutoIa: true };
      }

      const iaAfiliada = await this.consultarProdutoIa(dados.urlAfiliada);
      if (
        iaAfiliada.status === 'SUCESSO' ||
        iaAfiliada.status === 'INDISPONIVEL'
      ) {
        return { ...iaAfiliada, urlConsultada: 'AFILIADA', viaProdutoIa: true };
      }

      return {
        status: 'FALHOU',
        motivo: `Direto original: ${original.motivo} Direto afiliado: ${afiliada.motivo} Produto IA original: ${iaOriginal.motivo} Produto IA afiliado: ${iaAfiliada.motivo}`,
      };
    }

    if (original.status === 'INDISPONIVEL') {
      return { ...original, urlConsultada: 'ORIGINAL', viaProdutoIa: false };
    }

    const iaOriginal = await this.consultarProdutoIa(dados.urlOriginal);
    if (
      iaOriginal.status === 'SUCESSO' ||
      iaOriginal.status === 'INDISPONIVEL'
    ) {
      return { ...iaOriginal, urlConsultada: 'ORIGINAL', viaProdutoIa: true };
    }

    return {
      status: 'FALHOU',
      motivo: `Consulta direta: ${original.motivo} Produto IA: ${iaOriginal.motivo}`,
      urlConsultada: 'ORIGINAL',
      viaProdutoIa: true,
    };
  }
}
