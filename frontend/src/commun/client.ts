export type EtatConnexion = "connexion" | "ouverte" | "perdue";

export interface SocketMinimal {
  onopen: (() => void) | null;
  onmessage: ((e: { data: unknown }) => void) | null;
  onclose: (() => void) | null;
  onerror: (() => void) | null;
  send(donnees: string): void;
  close(): void;
  readyState: number;
}

export interface OptionsClient {
  url: string;
  surMessage: (message: unknown) => void;
  surEtat: (etat: EtatConnexion) => void;
  /** Message à envoyer dès l'ouverture (authentification de la scène, D38). */
  authentification?: () => object | null;
  creerSocket?: (url: string) => SocketMinimal;
  delais?: number[];
  intervallePing?: number;
  delaiPerte?: number;
}

const OUVERT = 1;

/**
 * Connexion WebSocket qui se rétablit toute seule (protocole §4.2, §7 ; REC-21).
 * - battement (ping) toutes les 15 s ; sans AUCUN message reçu pendant 30 s, la connexion est jugée perdue ;
 * - reconnexion avec des délais croissants : 0,5 s, 1 s, 2 s, puis 5 s au maximum.
 */
export class ClientWS {
  private socket: SocketMinimal | null = null;
  private tentative = 0;
  private derniereReception = 0;
  private minuteurPing: ReturnType<typeof setInterval> | null = null;
  private minuteurSurveillance: ReturnType<typeof setInterval> | null = null;
  private minuteurReconnexion: ReturnType<typeof setTimeout> | null = null;
  private arrete = false;
  private readonly delais: number[];
  private readonly intervallePing: number;
  private readonly delaiPerte: number;

  constructor(private options: OptionsClient) {
    this.delais = options.delais ?? [500, 1000, 2000, 5000];
    this.intervallePing = options.intervallePing ?? 15000;
    this.delaiPerte = options.delaiPerte ?? 30000;
  }

  connecter(): void {
    this.arrete = false;
    this.options.surEtat("connexion");
    const creer = this.options.creerSocket ?? ((url: string) => new WebSocket(url) as unknown as SocketMinimal);
    const socket = creer(this.options.url);
    this.socket = socket;
    socket.onopen = () => {
      this.tentative = 0;
      this.derniereReception = Date.now();
      const auth = this.options.authentification?.();
      if (auth) socket.send(JSON.stringify(auth));
      this.options.surEtat("ouverte");
      this.demarrerSurveillance();
    };
    socket.onmessage = (evenement) => {
      this.derniereReception = Date.now();
      try {
        this.options.surMessage(JSON.parse(String(evenement.data)));
      } catch {
        // message illisible : ignoré, la connexion continue
      }
    };
    socket.onclose = () => this.perdue(socket);
    socket.onerror = () => this.perdue(socket);
  }

  envoyer(message: object): boolean {
    if (this.socket && this.socket.readyState === OUVERT) {
      this.socket.send(JSON.stringify(message));
      return true;
    }
    return false;
  }

  fermer(): void {
    this.arrete = true;
    this.arreterSurveillance();
    if (this.minuteurReconnexion) clearTimeout(this.minuteurReconnexion);
    this.socket?.close();
    this.socket = null;
  }

  private demarrerSurveillance(): void {
    this.arreterSurveillance();
    this.minuteurPing = setInterval(() => this.envoyer({ type: "ping" }), this.intervallePing);
    this.minuteurSurveillance = setInterval(() => {
      if (Date.now() - this.derniereReception > this.delaiPerte && this.socket) {
        const socket = this.socket;
        socket.close(); // le serveur ne répond plus : on bascule en reconnexion
        this.perdue(socket);
      }
    }, 1000);
  }

  private arreterSurveillance(): void {
    if (this.minuteurPing) clearInterval(this.minuteurPing);
    if (this.minuteurSurveillance) clearInterval(this.minuteurSurveillance);
    this.minuteurPing = this.minuteurSurveillance = null;
  }

  private perdue(socket: SocketMinimal): void {
    if (this.arrete || socket !== this.socket) return; // un ancien socket ne déclenche rien
    this.socket = null;
    this.arreterSurveillance();
    this.options.surEtat("perdue");
    const delai = this.delais[Math.min(this.tentative, this.delais.length - 1)] ?? 5000;
    this.tentative += 1;
    this.minuteurReconnexion = setTimeout(() => this.connecter(), delai);
  }
}
