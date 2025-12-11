import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api.service';
import { Paginated, Player } from '../../models';

@Component({
  selector: 'app-players',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './players.component.html',
  styleUrls: ['./players.component.css']
})
export class PlayersComponent implements OnInit {
  players: Player[] = [];
  team_id = '';
  position = '';
  loading = false;

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading = true;
    this.api.listPlayers({ team_id: this.team_id || undefined, position: this.position || undefined })
      .subscribe((res: Paginated<Player>) => {
        this.players = res.items;
        this.loading = false;
      });
  }
}
