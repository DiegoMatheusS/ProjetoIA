import { VerificadorPrecosOfertasService } from './verificador-precos-ofertas.service';

type ExtratorTeste = {
  extrairPrecoEstruturado(
    html: string,
    url?: URL,
  ): {
    preco: number | null;
    origem: 'JSON_LD' | 'META' | 'JSON_EMBUTIDO' | 'HTML_MARKETPLACE' | null;
    indisponivel: boolean;
  };
  precisaConfirmacaoProdutoIa(
    precoAtual: number | undefined,
    precoEncontrado: number,
  ): boolean;
  extrairCodigoMarketplace(url: string): string | null;
};

describe('VerificadorPrecosOfertasService', () => {
  const service = new VerificadorPrecosOfertasService();
  const extrator = service as unknown as ExtratorTeste;

  it('extrai preço confiável de Offer em JSON-LD', () => {
    const html = `
      <html><head>
        <script type="application/ld+json">
          {
            "@context":"https://schema.org",
            "@type":"Product",
            "name":"Produto teste",
            "offers":{"@type":"Offer","price":"3699.90","availability":"https://schema.org/InStock"}
          }
        </script>
      </head></html>`;

    expect(extrator.extrairPrecoEstruturado(html)).toEqual({
      preco: 3699.9,
      origem: 'JSON_LD',
      indisponivel: false,
    });
  });

  it('aceita meta product:price:amount quando não existe JSON-LD utilizável', () => {
    const html =
      '<html><head><meta property="product:price:amount" content="1.299,90"></head></html>';

    expect(extrator.extrairPrecoEstruturado(html)).toEqual({
      preco: 1299.9,
      origem: 'META',
      indisponivel: false,
    });
  });

  it('detecta indisponibilidade estruturada sem inventar preço', () => {
    const html = `
      <script type="application/ld+json">
        {"@type":"Product","offers":{"@type":"Offer","availability":"https://schema.org/OutOfStock"}}
      </script>`;

    expect(extrator.extrairPrecoEstruturado(html)).toEqual({
      preco: null,
      origem: null,
      indisponivel: true,
    });
  });

  it('extrai preço atual de JSON de hidratação e ignora preço antigo', () => {
    const html = `
      <script id="__NEXT_DATA__" type="application/json">
        {
          "props": {
            "pageProps": {
              "product": {
                "originalPrice": 2999.90,
                "currentPrice": {"value": 2571.22}
              }
            }
          }
        }
      </script>`;

    expect(
      extrator.extrairPrecoEstruturado(
        html,
        new URL('https://www.magazineluiza.com.br/produto/p/123'),
      ),
    ).toEqual({
      preco: 2571.22,
      origem: 'JSON_EMBUTIDO',
      indisponivel: false,
    });
  });

  it('extrai preço principal do HTML do Mercado Livre', () => {
    const html = `
      <div class="ui-pdp-price__second-line">
        <span class="andes-money-amount">
          <span class="andes-money-amount__currency-symbol">R$</span>
          <span class="andes-money-amount__fraction">2.099</span>
          <span class="andes-money-amount__cents">00</span>
        </span>
      </div>`;

    expect(
      extrator.extrairPrecoEstruturado(
        html,
        new URL('https://produto.mercadolivre.com.br/MLB-123'),
      ),
    ).toEqual({
      preco: 2099,
      origem: 'HTML_MARKETPLACE',
      indisponivel: false,
    });
  });

  it('prefere preço no Pix no HTML do Magalu', () => {
    const html = `
      <main>
        <h1>Placa-mãe teste</h1>
        <span>R$ 2.858,22</span>
        <div>Preço <strong>R$ 2.571,22</strong> no Pix</div>
        <div>Ou R$ 2.706,55 em 10x de R$ 270,66 sem juros</div>
      </main>`;

    expect(
      extrator.extrairPrecoEstruturado(
        html,
        new URL('https://www.magazineluiza.com.br/produto/p/123'),
      ),
    ).toEqual({
      preco: 2571.22,
      origem: 'HTML_MARKETPLACE',
      indisponivel: false,
    });
  });

  it('converte preço escalado da Shopee em JSON embutido', () => {
    const html = `
      <script type="application/json" id="__NEXT_DATA__">
        {"product":{"price_before_discount":199900000,"price":177455000}}
      </script>`;

    expect(
      extrator.extrairPrecoEstruturado(
        html,
        new URL('https://shopee.com.br/produto-i.1.2'),
      ),
    ).toEqual({
      preco: 1774.55,
      origem: 'JSON_EMBUTIDO',
      indisponivel: false,
    });
  });

  it('não usa frete da Shopee como preço do produto no fallback HTML', () => {
    const html = `
      <main>
        <div>R$ 1.774,55</div>
        <h1>Produto teste</h1>
        <div>Frete grátis R$ 8,65 com cupom</div>
      </main>`;

    expect(
      extrator.extrairPrecoEstruturado(
        html,
        new URL('https://shopee.com.br/produto-i.1.2'),
      ),
    ).toEqual({
      preco: 1774.55,
      origem: 'HTML_MARKETPLACE',
      indisponivel: false,
    });
  });
  it('exige confirmação da Produto IA quando a variação passa de 35%', () => {
    expect(extrator.precisaConfirmacaoProdutoIa(1000, 640)).toBe(true);
    expect(extrator.precisaConfirmacaoProdutoIa(1000, 650)).toBe(false);
    expect(extrator.precisaConfirmacaoProdutoIa(1000, 1350)).toBe(false);
    expect(extrator.precisaConfirmacaoProdutoIa(1000, 1350.01)).toBe(true);
  });

  it('extrai o código do item para validar redirecionamento de marketplace', () => {
    expect(
      extrator.extrairCodigoMarketplace(
        'https://www.magazinevoce.com.br/loja/produto/p/ea444h39dd/in/pcvd/?seller_id=kabum',
      ),
    ).toBe('ea444h39dd');
    expect(
      extrator.extrairCodigoMarketplace(
        'https://produto.mercadolivre.com.br/MLB-1234567890-produto-_JM',
      ),
    ).toBe('mlb1234567890');
  });

});
